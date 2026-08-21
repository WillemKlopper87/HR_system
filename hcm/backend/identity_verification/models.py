from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from core_hr.base import TimestampedModel
from core_hr.models import Employee


class BiometricEnrollment(TimestampedModel):
    """POPIA (s26/27) treats biometric data as "special personal
    information" — a stricter bar than this system's generic Restricted
    tier (pay, comp proposals, ID number). Gated by its own dedicated
    consent purpose (rbac_audit.ConsentRecord.Purpose.BIOMETRIC), checked
    in services.py — not the generic P/I/S/R tier grants, which weren't
    designed around this kind of data. Stores only the derived 128-float
    face descriptor, never the enrollment photo itself: face detection and
    descriptor extraction run client-side (face-api.js) so the raw image
    never leaves the employee's browser. Re-enrollment overwrites the
    descriptor on this same row — simple_history's HistoricalRecords
    preserves prior values for audit, so there's no need for a separate
    "superseded" bookkeeping field."""

    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name="biometric_enrollment")
    descriptor = models.JSONField()
    enrolled_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="enrollments_captured"
    )
    # C1 part 3 (employment exit access cascade, design spec §6.1/§6.3):
    # deactivated -- never deleted -- when a person is suspended or exits,
    # so a departed or suspended employee can't pass a liveness check
    # (services.py::run_liveness_check checks this). "The one thing that
    # is deactivated rather than kept usable is the biometric descriptor
    # ... there is no audit reason to keep a departed person's face
    # template live" -- the descriptor value itself is left untouched
    # (not wiped), simple_history already preserves prior values, and a
    # LIFT_SUSPENSION flips this back to True.
    active = models.BooleanField(default=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Biometric enrollment for {self.employee.employee_number}"


class LivenessCheck(TimestampedModel):
    """One check-in attempt: a face descriptor compared against the
    employee's BiometricEnrollment, plus (same user action) an optional
    device geolocation compared against their assigned Location's office
    geofence — policy requires 2 in-office days/week (identity_verification/
    geo.py::REQUIRED_OFFICE_DAYS_PER_WEEK). A mismatch or no-face-detected
    result is NEVER auto-flagged as confirmed fraud — it's queued for
    hr_admin review (review_status=PENDING); only a human sets
    CONFIRMED_MISMATCH. Facial recognition has well-documented accuracy/
    bias limitations, and this system is Employment-Equity-focused, so an
    automated "this looks like a ghost employee" decision would be
    genuinely irresponsible without a human in the loop."""

    class Trigger(models.TextChoices):
        SELF = "self", "Self-initiated"
        HR_REQUESTED = "hr_requested", "HR-requested"

    class Outcome(models.TextChoices):
        MATCH = "match", "Matched enrolled identity"
        NO_MATCH = "no_match", "Did not match enrolled identity"
        NO_FACE_DETECTED = "no_face_detected", "No face detected in capture"

    class ReviewStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        PENDING = "pending", "Pending HR review"
        CONFIRMED_MATCH = "confirmed_match", "HR confirmed this is the enrolled employee"
        CONFIRMED_MISMATCH = "confirmed_mismatch", "HR confirmed this is NOT the enrolled employee"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="liveness_checks")
    trigger = models.CharField(max_length=20, choices=Trigger.choices, default=Trigger.SELF)
    requested_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="liveness_checks_requested"
    )
    match_distance = models.FloatField(null=True, blank=True)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    distance_from_office_m = models.FloatField(null=True, blank=True)
    # None = location unavailable/not granted, not "confirmed absent".
    at_office = models.BooleanField(null=True)

    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.NOT_REQUIRED)
    reviewed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="liveness_checks_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.get_outcome_display()} ({self.created_at:%Y-%m-%d})"
