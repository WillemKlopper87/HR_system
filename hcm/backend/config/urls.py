import logging

from django.contrib import admin
from django.core.cache import cache
from django.db import connections
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework.permissions import IsAuthenticated

from assessments.views import assessment_webhook

logger = logging.getLogger(__name__)


class IsHRAdminSchema(IsAuthenticated):
    """The schema/docs UI exposes every field name and endpoint shape in
    one place — operational/developer tooling, not an employee-facing
    feature, so it gets hr_admin's access bar rather than being open to
    any authenticated session."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        employee = get_request_employee(request)
        return employee is not None and has_role(employee, "hr_admin")


class HRAdminSchemaView(SpectacularAPIView):
    permission_classes = [IsHRAdminSchema]


class HRAdminSwaggerView(SpectacularSwaggerView):
    permission_classes = [IsHRAdminSchema]


def healthz(_request):
    """Process-up only — deliberately checks nothing else. A load balancer
    polling this every few seconds should never fail because Postgres had
    one slow query; that is exactly what /readyz is for."""
    return JsonResponse({"status": "ok"})


def readyz(_request):
    """Can this instance actually serve traffic: DB and cache both
    reachable. Every check runs even if an earlier one fails, so a caller
    sees the full picture in one request instead of fixing issues one at
    a time (H3 ops/observability)."""
    checks = {}

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — report any DB failure, not just specific ones
        checks["database"] = "unreachable"
        logger.warning("readyz: database check failed: %s", exc)

    try:
        marker = "readyz-probe"
        cache.set(marker, "1", timeout=5)
        checks["cache"] = "ok" if cache.get(marker) == "1" else "unreachable"
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = "unreachable"
        logger.warning("readyz: cache check failed: %s", exc)

    ready = all(v == "ok" for v in checks.values())
    return JsonResponse({"status": "ready" if ready else "not_ready", "checks": checks}, status=200 if ready else 503)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz),
    path("readyz", readyz),
    # Module APIs mount under /api/v1/ as sprints deliver them.
    path("api/v1/auth/", include("rbac_audit.urls")),
    path("api/v1/", include("core_hr.urls")),
    path("api/v1/", include("recruitment.urls")),
    path("api/v1/", include("performance.urls")),
    path("api/v1/", include("learning.urls")),
    path("api/v1/", include("compensation.urls")),
    path("api/v1/", include("assessments.urls")),
    path("api/v1/", include("identity_verification.urls")),
    path("api/v1/", include("ee_reporting.urls")),
    path("api/v1/", include("policies.urls")),
    path("api/v1/", include("notifications.urls")),
    path("api/v1/", include("establishment.urls")),
    # OpenAPI schema + Swagger UI (H3) — hr_admin only, see IsHRAdminSchema.
    path("api/schema/", HRAdminSchemaView.as_view(), name="schema"),
    path("api/docs/", HRAdminSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Inbound provider webhooks are versioned separately from the session-
    # authenticated /api/v1/ surface (Architecture-Design.md §6) — HMAC
    # signature verification is the auth here, not a Django session.
    path("webhooks/v1/assessments/", assessment_webhook, name="assessment-webhook"),
]

# No MEDIA_URL static() mount: django.views.static.serve has no RBAC/
# authentication layer at all, and the zero-config dev/CI path defaults
# DEBUG=True (config/settings.py), so mounting it would make every
# uploaded policy document fetchable by anyone who has the URL, logged in
# or not. policies.Policy.source_file is served exclusively through
# PolicyViewSet.download (authenticated, same permission + status-filtered
# queryset as the rest of the API) instead — see policies/views.py.
