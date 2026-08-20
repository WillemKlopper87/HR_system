from __future__ import annotations

import csv

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, serializers, viewsets
from rest_framework.pagination import CursorPagination
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .audit import log_access
from .drf import get_request_employee, int_query_param
from .models import AuditLogEntry, StepUpGrant, TOTPDevice
from .throttling import LOGIN_THROTTLES, TOTP_THROTTLES
from .permissions import active_roles_for, has_role
from .stepup import (
    StepUpError,
    confirm_totp_device,
    enroll_totp_device,
    has_active_step_up_grant,
    request_step_up,
    totp_provisioning_uri,
)
from .tiers import FieldTier


def _me_payload(request):
    """Shared by login and /me — the minimal identity + role set the SPA
    needs to decide what nav/actions to render. Field-level visibility is
    still enforced server-side by TieredModelSerializer on every resource
    endpoint; this is not a substitute for that."""
    employee = get_request_employee(request)
    if employee is None:
        return None
    roles = list(active_roles_for(employee).values_list("name", flat=True))
    return {
        "employee_id": employee.id,
        "employee_number": employee.employee_number,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "work_email": employee.work_email,
        "roles": roles,
    }


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    """Ensures the csrftoken cookie is set so the SPA can read it and send
    it back as X-CSRFToken on login/logout and every mutating request —
    DRF's SessionAuthentication enforces CSRF once a session exists."""
    get_token(request)
    return Response({"detail": "CSRF cookie set"})


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes(LOGIN_THROTTLES)
def login_view(request):
    username = request.data.get("username", "")
    password = request.data.get("password", "")
    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response({"detail": "Invalid credentials"}, status=401)

    login(request, user)
    payload = _me_payload(request)
    if payload is None:
        logout(request)
        return Response({"detail": "This account has no linked employee record"}, status=403)

    log_access(
        actor=get_request_employee(request),
        action=AuditLogEntry.Action.LOGIN,
        entity_type="auth.User",
        entity_id=user.pk,
        field_tier=FieldTier.PUBLIC,
    )
    return Response(payload)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response({"detail": "Logged out"})


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    payload = _me_payload(request)
    if payload is None:
        return Response({"detail": "This account has no linked employee record"}, status=403)
    return Response(payload)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def totp_enroll(request):
    """Starts (or restarts) authenticator-app enrollment for step-up MFA.
    Returns the raw secret too, not just the provisioning URI, since a
    demo/local-dev user without a real authenticator app on hand needs a
    way to compute codes manually (see hcm/README.md)."""
    employee = get_request_employee(request)
    device = enroll_totp_device(employee)
    return Response({"secret": device.secret, "provisioning_uri": totp_provisioning_uri(device)})


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes(TOTP_THROTTLES)
def totp_confirm(request):
    employee = get_request_employee(request)
    try:
        confirm_totp_device(employee, code=request.data.get("code", ""))
    except StepUpError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"detail": "Authenticator device confirmed."})


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def totp_status(request):
    employee = get_request_employee(request)
    device = TOTPDevice.objects.filter(employee=employee).first()
    return Response({
        "enrolled": device is not None and device.confirmed_at is not None,
        "pending_confirmation": device is not None and device.confirmed_at is None,
    })


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes(TOTP_THROTTLES)
def step_up_request_view(request):
    """The single call that both verifies the TOTP code AND records the
    business-justification reason — see stepup.py::request_step_up."""
    employee = get_request_employee(request)
    try:
        grant = request_step_up(
            employee,
            code=request.data.get("code", ""),
            scope=request.data.get("scope", StepUpGrant.Scope.PAYROLL_DATA),
            reason=request.data.get("reason", ""),
            reason_detail=request.data.get("reason_detail", ""),
        )
    except StepUpError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"scope": grant.scope, "expires_at": grant.expires_at})


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def step_up_status_view(request):
    employee = get_request_employee(request)
    scope = request.query_params.get("scope", StepUpGrant.Scope.PAYROLL_DATA)
    return Response({"active": has_active_step_up_grant(employee, scope=scope)})


# --- Audit-log viewer (H3) ---------------------------------------------------
# The auditor role's own seed description: "Read-only everywhere, including
# the audit log itself — every auditor read is itself audited." So every
# list/export call here writes its own AuditLogEntry, same as any other
# sensitive read in the app.


class AuditLogEntrySerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    actor_employee_number = serializers.SerializerMethodField()
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    field_tier_display = serializers.CharField(source="get_field_tier_display", read_only=True)

    class Meta:
        model = AuditLogEntry
        fields = [
            "id", "timestamp", "actor", "actor_name", "actor_employee_number", "action", "action_display",
            "entity_type", "entity_id", "field_tier", "field_tier_display", "fields_touched",
            "request_id", "ip_address",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj) -> str:
        return f"{obj.actor.first_name} {obj.actor.last_name}" if obj.actor_id else "system"

    def get_actor_employee_number(self, obj) -> str | None:
        return obj.actor.employee_number if obj.actor_id else None


class IsHRAdminOrAuditor(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        employee = get_request_employee(request)
        return employee is not None and (has_role(employee, "hr_admin") or has_role(employee, "auditor"))


def _filtered_audit_log(request):
    qs = AuditLogEntry.objects.select_related("actor").all()
    actor_id = int_query_param(request, "actor")
    if actor_id is not None:
        qs = qs.filter(actor_id=actor_id)
    entity_type = request.query_params.get("entity_type")
    if entity_type:
        qs = qs.filter(entity_type__icontains=entity_type)
    action = request.query_params.get("action")
    if action:
        qs = qs.filter(action=action)
    field_tier = request.query_params.get("field_tier")
    if field_tier:
        qs = qs.filter(field_tier=field_tier)
    date_from = parse_date(request.query_params.get("date_from") or "")
    if date_from:
        qs = qs.filter(timestamp__date__gte=date_from)
    date_to = parse_date(request.query_params.get("date_to") or "")
    if date_to:
        qs = qs.filter(timestamp__date__lte=date_to)
    return qs


class _AuditLogCursorPagination(CursorPagination):
    """`AuditLogEntry.timestamp` predates the TimestampedModel convention
    (`created_at`) the project-wide default pagination ordering assumes.

    `-id` is a tiebreaker: `timestamp` alone isn't unique enough (entries
    created in quick succession can share a value), and DRF's cursor
    pagination needs a fully deterministic ordering to avoid skipping or
    duplicating rows across pages when ties occur at a page boundary."""

    ordering = ("-timestamp", "-id")


class AuditLogEntryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only, filterable, hr_admin/auditor only. No detail route — a
    single entry in isolation is meaningless without the same filters that
    found it, and there is nothing to act on (append-only, see the model)."""

    serializer_class = AuditLogEntrySerializer
    permission_classes = [IsHRAdminOrAuditor]
    pagination_class = _AuditLogCursorPagination

    def get_queryset(self):
        return _filtered_audit_log(self.request)

    def list(self, request, *args, **kwargs):
        log_access(
            actor=get_request_employee(request), action=AuditLogEntry.Action.READ_SENSITIVE,
            entity_type="rbac_audit.AuditLogEntry", entity_id="list", field_tier=FieldTier.RESTRICTED,
            fields_touched=f"filters={dict(request.query_params)}",
        )
        return super().list(request, *args, **kwargs)


@extend_schema(responses={200: OpenApiTypes.BINARY})
@api_view(["GET"])
@permission_classes([IsHRAdminOrAuditor])
def audit_log_export(request):
    entries = _filtered_audit_log(request).order_by("-timestamp", "-id")
    log_access(
        actor=get_request_employee(request), action=AuditLogEntry.Action.EXPORT,
        entity_type="rbac_audit.AuditLogEntry", entity_id="export", field_tier=FieldTier.RESTRICTED,
        fields_touched=f"csv export, filters={dict(request.query_params)}",
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="audit-log.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "timestamp", "actor_employee_number", "actor_name", "action", "entity_type", "entity_id",
        "field_tier", "fields_touched", "request_id", "ip_address",
    ])
    for entry in entries:
        writer.writerow([
            entry.timestamp.isoformat(),
            entry.actor.employee_number if entry.actor_id else "",
            f"{entry.actor.first_name} {entry.actor.last_name}" if entry.actor_id else "system",
            entry.action, entry.entity_type, entry.entity_id, entry.field_tier,
            entry.fields_touched, entry.request_id, entry.ip_address or "",
        ])
    return response
