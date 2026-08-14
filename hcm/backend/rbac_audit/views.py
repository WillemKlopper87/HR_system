from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .audit import log_access
from .drf import get_request_employee
from .models import AuditLogEntry, StepUpGrant, TOTPDevice
from .permissions import active_roles_for
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


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    """Ensures the csrftoken cookie is set so the SPA can read it and send
    it back as X-CSRFToken on login/logout and every mutating request —
    DRF's SessionAuthentication enforces CSRF once a session exists."""
    get_token(request)
    return Response({"detail": "CSRF cookie set"})


@api_view(["POST"])
@permission_classes([AllowAny])
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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response({"detail": "Logged out"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    payload = _me_payload(request)
    if payload is None:
        return Response({"detail": "This account has no linked employee record"}, status=403)
    return Response(payload)


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


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def totp_confirm(request):
    employee = get_request_employee(request)
    try:
        confirm_totp_device(employee, code=request.data.get("code", ""))
    except StepUpError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"detail": "Authenticator device confirmed."})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def totp_status(request):
    employee = get_request_employee(request)
    device = TOTPDevice.objects.filter(employee=employee).first()
    return Response({
        "enrolled": device is not None and device.confirmed_at is not None,
        "pending_confirmation": device is not None and device.confirmed_at is None,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def step_up_status_view(request):
    employee = get_request_employee(request)
    scope = request.query_params.get("scope", StepUpGrant.Scope.PAYROLL_DATA)
    return Response({"active": has_active_step_up_grant(employee, scope=scope)})
