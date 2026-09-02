"""Probation tracking. Split out of models.py (HR_Code_report.md M5) -- no
behavior change; see core_hr/models/__init__.py for the app's overall split."""
from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from ..base import TimestampedModel
from .core import Employee


class ProbationPeriod(TimestampedModel):
    """One probation window per hire (or per fresh-probation event, e.g. a
    rehire) — the Code on integrating EE into HR practice's probation
    section ("a written policy, regular documented reviews signed by the
    employee, completion rates by designated group and exit interviews
    for non-confirmations"), deliberately split out of the fixed-term
    contract-tracking slice (C1 pt 2) since probation applies to
    permanent hires too, not just fixed-term ones.

    No row is created automatically at hire — same "no synthetic
    pending-nothing-happened row" posture ContractRenewalDecision's own
    docstring states; hr_admin/line_manager open one explicitly."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        CONFIRMED = "confirmed", "Confirmed"
        EXTENDED = "extended", "Extended"
        TERMINATED = "terminated", "Terminated (not confirmed)"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="probation_periods")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    outcome_at = models.DateTimeField(null=True, blank=True)
    outcome_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    outcome_notes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.employee.employee_number}: probation {self.start_date}–{self.end_date} ({self.status})"


class ProbationReview(TimestampedModel):
    """One documented review within a ProbationPeriod. `employee_signed_at`
    is the Code's "reviews ... signed by the employee" requirement —
    nullable because a review can be recorded before the employee has
    countersigned it, the same "record now, evidence catches up" shape
    EEForumMeeting's minutes upload uses."""

    class Recommendation(models.TextChoices):
        CONTINUE = "continue", "Continue probation"
        EXTEND = "extend", "Recommend extension"
        CONFIRM = "confirm", "Recommend confirmation"
        TERMINATE = "terminate", "Recommend termination"

    probation_period = models.ForeignKey(ProbationPeriod, on_delete=models.CASCADE, related_name="reviews")
    review_date = models.DateField()
    reviewed_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="probation_reviews_conducted")
    recommendation = models.CharField(max_length=20, choices=Recommendation.choices)
    comments = models.TextField(blank=True)
    employee_signed_at = models.DateTimeField(null=True, blank=True)
    # SHA-256 of the immutable review payload at countersignature time.
    employee_signature_sha256 = models.CharField(max_length=64, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-review_date"]

    def __str__(self):
        return f"{self.probation_period.employee.employee_number}: review {self.review_date} ({self.recommendation})"
