from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from notifications.services import employees_with_role, notify_many
from rbac_audit.models import ConsentRecord

from .geo import OFFICE_GEOFENCE_RADIUS_M, REQUIRED_OFFICE_DAYS_PER_WEEK, haversine_distance_m
from .matching import DescriptorError, MATCH_THRESHOLD, euclidean_distance
from .models import BiometricEnrollment, LivenessCheck

CONSENT_HINT = "Biometric consent has not been captured for this employee — POST /api/v1/liveness/consent/ first."


class ConsentRequiredError(ValueError):
    pass


class EnrollmentRequiredError(ValueError):
    pass


class ReviewError(ValueError):
    pass


def _has_biometric_consent(employee) -> bool:
    return ConsentRecord.objects.filter(
        employee=employee, purpose=ConsentRecord.Purpose.BIOMETRIC, withdrawn_at__isnull=True
    ).exists()


@transaction.atomic
def enroll_employee(*, employee, descriptor: list[float], actor=None) -> BiometricEnrollment:
    if not _has_biometric_consent(employee):
        raise ConsentRequiredError(CONSENT_HINT)
    # active=True in defaults: a fresh enrol/re-enrol always (re)activates
    # -- e.g. a rehired employee whose old enrolment was deactivated by
    # C1 part 3's exit cascade must not stay locked out forever.
    enrollment, _ = BiometricEnrollment.objects.update_or_create(
        employee=employee, defaults={"descriptor": descriptor, "enrolled_by": actor, "active": True}
    )
    return enrollment


def _office_distance(employee, latitude, longitude):
    if latitude is None or longitude is None:
        return None, None
    version = employee.current_version
    location = version.location if version is not None else None
    if location is None or location.latitude is None or location.longitude is None:
        return None, None
    distance = haversine_distance_m(
        float(latitude), float(longitude), float(location.latitude), float(location.longitude)
    )
    return distance, distance <= OFFICE_GEOFENCE_RADIUS_M


@transaction.atomic
def run_liveness_check(
    *, employee, descriptor: list[float] | None, latitude=None, longitude=None,
    trigger=LivenessCheck.Trigger.SELF, requested_by=None,
) -> LivenessCheck:
    if not _has_biometric_consent(employee):
        raise ConsentRequiredError(CONSENT_HINT)
    enrollment = BiometricEnrollment.objects.filter(employee=employee).first()
    if enrollment is None:
        raise EnrollmentRequiredError("This employee has no biometric enrollment on file yet.")
    if not enrollment.active:
        # C1 part 3: a suspension or exit deactivates the enrolment
        # (identity_verification/exit_handlers.py) so a departed or
        # suspended person genuinely cannot pass a check, not just "loses
        # role-gated access to the result".
        raise EnrollmentRequiredError("This employee's biometric enrollment is suspended.")

    if descriptor is None:
        outcome = LivenessCheck.Outcome.NO_FACE_DETECTED
        distance = None
    else:
        try:
            distance = euclidean_distance(enrollment.descriptor, descriptor)
        except DescriptorError:
            distance = None
        outcome = (
            LivenessCheck.Outcome.MATCH
            if distance is not None and distance < MATCH_THRESHOLD
            else LivenessCheck.Outcome.NO_MATCH
        )

    distance_from_office, at_office = _office_distance(employee, latitude, longitude)
    review_status = (
        LivenessCheck.ReviewStatus.NOT_REQUIRED
        if outcome == LivenessCheck.Outcome.MATCH
        else LivenessCheck.ReviewStatus.PENDING
    )

    check = LivenessCheck.objects.create(
        employee=employee, trigger=trigger, requested_by=requested_by, match_distance=distance, outcome=outcome,
        latitude=latitude, longitude=longitude, distance_from_office_m=distance_from_office, at_office=at_office,
        review_status=review_status,
    )
    if review_status == LivenessCheck.ReviewStatus.PENDING:
        notify_many(
            employees_with_role("hr_admin"), kind="liveness_flag",
            title=f"Liveness check flagged for review: {employee.employee_number}",
            body=f"Outcome: {check.get_outcome_display()}.",
            link="/workforce-integrity",
        )
    return check


def resolve_review(check: LivenessCheck, *, reviewer, decision: str, notes: str = "") -> LivenessCheck:
    if check.review_status != LivenessCheck.ReviewStatus.PENDING:
        raise ReviewError("Only a pending check can be reviewed.")
    if decision not in (LivenessCheck.ReviewStatus.CONFIRMED_MATCH, LivenessCheck.ReviewStatus.CONFIRMED_MISMATCH):
        raise ReviewError("decision must be confirmed_match or confirmed_mismatch.")
    check.review_status = decision
    check.reviewed_by = reviewer
    check.reviewed_at = timezone.now()
    check.review_notes = notes
    check.save(update_fields=["review_status", "reviewed_by", "reviewed_at", "review_notes"])
    return check


def weekly_office_attendance(employee, *, reference_date=None) -> dict:
    """Distinct in-office days (at_office=True) in the ISO week containing
    reference_date (defaults to today). Policy: 2/week
    (geo.py::REQUIRED_OFFICE_DAYS_PER_WEEK) — a documented constant until
    the user's planned "policy section" sprint gives it a real home."""
    ref = reference_date or timezone.localdate()
    week_start = ref - timedelta(days=ref.weekday())
    week_end = week_start + timedelta(days=7)
    days = (
        LivenessCheck.objects.filter(
            employee=employee, at_office=True, created_at__date__gte=week_start, created_at__date__lt=week_end,
        )
        .dates("created_at", "day")
        .count()
    )
    return {
        "week_start": week_start,
        "days_in_office": days,
        "required_days": REQUIRED_OFFICE_DAYS_PER_WEEK,
        "compliant": days >= REQUIRED_OFFICE_DAYS_PER_WEEK,
    }
