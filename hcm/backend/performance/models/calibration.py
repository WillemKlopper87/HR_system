"""Calibration / moderation (C6, NEXT_AGENT_BRIEF.md §7.3 #20).

A committee-style consistency check across a cohort of already-finalised
`PerformanceAgreement`s, before their scores are treated as the org's
official record. Deliberately hr_admin recording an offline meeting's
outcome, not a live multi-party workflow -- see design spec §2.3.

`CalibrationAdjustment` is the audit trail the guardrail demands: never a
silent overwrite of a signed `final_score` (spec §2.4). It is immutable
(create-only -- no update/delete route in the API, the same shape
`AgreementSignature` already uses) and required to carry a reason even when
nothing changed ("reviewed, no change needed" is itself a recorded fact).
"""
from __future__ import annotations

from django.db import models

from core_hr.base import TimestampedModel
from core_hr.models import Department, Employee

from .agreements import PerformanceAgreement, PerformancePeriod


class CalibrationSession(TimestampedModel):
    """One cohort's moderation round for one period. `department` is nullable
    -- blank means an org-wide session -- following `AgreementTemplate`'s own
    "empty targeting = everyone" precedent (spec §2.2)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        COMPLETED = "completed", "Completed"

    period = models.ForeignKey(PerformancePeriod, on_delete=models.PROTECT, related_name="calibration_sessions")
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="calibration_sessions",
        help_text="Blank = org-wide cohort",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    meeting_date = models.DateField(null=True, blank=True)
    participants_note = models.CharField(
        max_length=500, blank=True, help_text="Free text: who attended (Heads/managers)"
    )
    summary = models.TextField(
        blank=True, help_text="Overall committee notes, e.g. 'distribution reviewed, no changes needed'"
    )
    convened_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="calibration_sessions_convened"
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        scope = self.department.name if self.department_id else "Org-wide"
        return f"Calibration {self.period.name} — {scope} ({self.get_status_display()})"


class CalibrationAdjustment(TimestampedModel):
    """One recorded outcome for one agreement within a session. `new_score`
    null means "reviewed, no change" -- still a real, reasoned record that the
    agreement was looked at. `previous_score` is captured at write time so the
    row is self-contained even if `final_score` moves again later. No
    update/delete route exists in the API (services/calibration.py docstring);
    a correction is a new, separately-reasoned row, not an edited one."""

    session = models.ForeignKey(CalibrationSession, on_delete=models.CASCADE, related_name="adjustments")
    agreement = models.ForeignKey(
        PerformanceAgreement, on_delete=models.PROTECT, related_name="calibration_adjustments"
    )
    previous_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    new_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    reason = models.TextField()
    adjusted_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="calibration_adjustments_made"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["session", "agreement"], name="one_calibration_outcome_per_agreement")
        ]

    def __str__(self):
        change = "no change" if self.new_score is None else f"{self.previous_score} → {self.new_score}"
        return f"Calibration outcome for {self.agreement} ({change})"
