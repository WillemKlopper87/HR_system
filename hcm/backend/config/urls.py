from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from assessments.views import assessment_webhook


def healthz(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz),
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
