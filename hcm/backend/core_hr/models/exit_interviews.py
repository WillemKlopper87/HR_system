"""Exit interviews for departures and probation non-confirmations. Split
out of models.py (HR_Code_report.md M5) -- no behavior change; see
core_hr/models/__init__.py for the app's overall split."""
from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from ..base import TimestampedModel
from .core import Employee
from .probation import ProbationPeriod


class ExitInterview(TimestampedModel):
    """Code on integrating EE into HR practice: exit interviews for
    departures, and separately for probation non-confirmations (the same
    section's own cross-reference). Linked to at most one of
    employment_change (a genuine exit) or probation_period (a
    non-confirmation) -- both nullable so a record can exist even if the
    triggering row is later deleted, and neither is required so an
    interview can be logged before the formal exit paperwork catches up."""

    class Reason(models.TextChoices):
        COMPENSATION = "compensation", "Compensation"
        CAREER_GROWTH = "career_growth", "Career growth"
        MANAGEMENT = "management", "Management or relationship with manager"
        WORK_LIFE_BALANCE = "work_life_balance", "Work-life balance"
        RELOCATION = "relocation", "Relocation"
        HEALTH = "health", "Health or personal"
        ROLE_FIT = "role_fit", "Role fit"
        OTHER = "other", "Other"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="exit_interviews")
    employment_change = models.ForeignKey(
        "EmploymentChange", null=True, blank=True, on_delete=models.SET_NULL, related_name="exit_interviews"
    )
    probation_period = models.ForeignKey(
        ProbationPeriod, null=True, blank=True, on_delete=models.SET_NULL, related_name="exit_interviews"
    )
    interview_date = models.DateField()
    conducted_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="exit_interviews_conducted")
    primary_reason = models.CharField(max_length=30, choices=Reason.choices)
    would_recommend_employer = models.BooleanField(null=True, blank=True)
    comments = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-interview_date"]

    def __str__(self):
        return f"{self.employee.employee_number}: exit interview {self.interview_date}"
