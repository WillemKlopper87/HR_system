"""Registered with core_hr's access-cascade registry from
IdentityVerificationConfig.ready() (see apps.py). core_hr dispatches by
name without ever importing this app -- see core_hr/access_cascade.py's
module docstring for why.

`BiometricEnrollment.employee` is a OneToOneField, so there is at most one
row per employee; these are simple flip-the-flag operations, not bulk
queries over many rows per person."""
from __future__ import annotations

from .models import BiometricEnrollment


def suspend_biometric_enrollment(employee) -> int:
    """Cascade step 3 (design spec §6.1): suspend the enrolment so a
    departed or suspended person cannot pass a liveness check. Returns 1
    if there was an active enrolment to suspend, 0 otherwise (including
    "no enrolment on file at all" -- an employee with none doesn't break
    the cascade, there's simply nothing to do)."""
    updated = BiometricEnrollment.objects.filter(employee=employee, active=True).update(active=False)
    return updated


def restore_biometric_enrollment(employee) -> int:
    """The LIFT_SUSPENSION inverse (design spec §6.2)."""
    updated = BiometricEnrollment.objects.filter(employee=employee, active=False).update(active=True)
    return updated
