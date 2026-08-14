from __future__ import annotations

from datetime import timedelta

import pyotp
from django.utils import timezone
from rest_framework import permissions

from .audit import log_access
from .drf import get_request_employee
from .models import AuditLogEntry, StepUpGrant, TOTPDevice
from .tiers import FieldTier

STEPUP_GRANT_MINUTES = 15


class StepUpError(ValueError):
    pass


def enroll_totp_device(employee) -> TOTPDevice:
    """(Re)starts enrollment with a fresh secret every time, unconfirmed —
    a half-finished enrollment (secret generated, first code never
    entered) never silently becomes a usable device. Re-enrolling replaces
    a prior confirmed device too (e.g. a lost phone), which is intentional:
    there's no separate "revoke my old device" step to forget."""
    device, _created = TOTPDevice.objects.update_or_create(
        employee=employee, defaults={"secret": pyotp.random_base32(), "confirmed_at": None},
    )
    return device


def totp_provisioning_uri(device: TOTPDevice, *, issuer: str = "Sentech HCM") -> str:
    return pyotp.TOTP(device.secret).provisioning_uri(name=device.employee.work_email, issuer_name=issuer)


def confirm_totp_device(employee, *, code: str) -> TOTPDevice:
    device = TOTPDevice.objects.filter(employee=employee).first()
    if device is None:
        raise StepUpError("No authenticator enrollment in progress — start enrollment first.")
    if not pyotp.TOTP(device.secret).verify(code, valid_window=1):
        raise StepUpError("Invalid code.")
    device.confirmed_at = timezone.now()
    device.save(update_fields=["confirmed_at"])
    return device


def request_step_up(
    employee, *, code: str, scope: str, reason: str, reason_detail: str = ""
) -> StepUpGrant:
    """The one entry point for obtaining a StepUpGrant — both the TOTP
    code and the justification are required together in this single call,
    so there's no way to satisfy the MFA check and the justification
    requirement as two independently-replayable steps."""
    device = TOTPDevice.objects.filter(employee=employee, confirmed_at__isnull=False).first()
    if device is None:
        raise StepUpError("No confirmed authenticator device on file — enroll one first.")
    if not pyotp.TOTP(device.secret).verify(code, valid_window=1):
        raise StepUpError("Invalid authentication code.")
    if scope not in StepUpGrant.Scope.values:
        raise StepUpError("Invalid scope.")
    if reason not in StepUpGrant.Reason.values:
        raise StepUpError("Invalid reason.")
    if reason == StepUpGrant.Reason.OTHER and not reason_detail.strip():
        raise StepUpError("A detail is required when the reason is 'Other'.")

    grant = StepUpGrant.objects.create(
        employee=employee, scope=scope, reason=reason, reason_detail=reason_detail,
        expires_at=timezone.now() + timedelta(minutes=STEPUP_GRANT_MINUTES),
    )
    log_access(
        actor=employee,
        action=AuditLogEntry.Action.STEP_UP_GRANTED,
        entity_type="rbac_audit.StepUpGrant",
        entity_id=grant.pk,
        field_tier=FieldTier.RESTRICTED,
        fields_touched=f"scope={scope};reason={reason}",
    )
    return grant


def has_active_step_up_grant(employee, *, scope: str) -> bool:
    if employee is None:
        return False
    return StepUpGrant.objects.filter(employee=employee, scope=scope, expires_at__gt=timezone.now()).exists()


class RequiresStepUpGrant(permissions.BasePermission):
    """Layered ON TOP OF a module's normal role-based permission class in
    permission_classes (DRF requires every listed class to pass) — this
    doesn't replace compensation.IsCompManagerOrHRAdmin or
    ee_reporting.EEReportingPermission, it adds a second, narrower bar for
    the specific Restricted-tier payroll models (Data-Dictionary.md).
    Subclass and set `scope`; do not instantiate this base class directly
    since `scope=None` would never match a real StepUpGrant.scope value."""

    scope: str | None = None
    message = "Step-up authentication required — verify your identity and state a business justification first."

    def has_permission(self, request, view):
        employee = get_request_employee(request)
        return has_active_step_up_grant(employee, scope=self.scope)


class RequiresPayrollStepUp(RequiresStepUpGrant):
    scope = StepUpGrant.Scope.PAYROLL_DATA
