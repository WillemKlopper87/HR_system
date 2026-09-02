"""System-detected data-quality exceptions. Split out of models.py
(HR_Code_report.md M5) -- no behavior change; see core_hr/models/__init__.py
for the app's overall split."""
from __future__ import annotations

from django.db import models

from ..base import TimestampedModel
from .core import Employee


class DataQualityException(TimestampedModel):
    class ExceptionType(models.TextChoices):
        MISSING_GRADE = "missing_grade", "Missing job grade"
        MISSING_DEMOGRAPHICS = "missing_demographics", "Missing demographics"
        ORPHAN_RECORD = "orphan_record", "Orphan record (no version history)"
        MISSING_CONTRACT_END_DATE = "missing_contract_end_date", "Fixed-term employee missing contract end date"
        # H3: org-wide checks registered from other apps' AppConfig.ready()
        # (data_quality.py's registry — same shape as rbac_audit/retention.py).
        # New types are added here, the shared-kernel model, rather than each
        # app owning its own choices set, the same way every log_access()
        # caller across the app writes AuditLogEntry.Action from one shared list.
        PERFORMANCE_OVERDUE = "performance_overdue", "Overdue performance stage"
        COMP_PROPOSAL_STALE = "comp_proposal_stale", "Compensation proposal awaiting review too long"
        MANDATORY_TRAINING_OVERDUE = "mandatory_training_overdue", "Overdue mandatory training"
        CRITICAL_POST_NO_SUCCESSOR = "critical_post_no_successor", "Critical post without a ready successor"
        PERFORMANCE_NO_CALIBRATION = "performance_no_calibration", "Final-signed agreement with no calibration session"
        COMP_CYCLE_OVERDUE = "comp_cycle_overdue", "Open compensation cycle past its period end with unresolved proposals"
        EE_MEASURE_OVERDUE = "ee_measure_overdue", "EE plan affirmative-action measure past its target date"

    employee = models.ForeignKey(
        Employee, related_name="data_quality_exceptions", on_delete=models.CASCADE
    )
    exception_type = models.CharField(max_length=30, choices=ExceptionType.choices)
    detail = models.TextField(blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-detected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "exception_type"],
                condition=models.Q(resolved_at__isnull=True),
                name="one_open_exception_per_employee_type",
            )
        ]

    def __str__(self):
        status = "open" if self.resolved_at is None else "resolved"
        return f"{self.employee.employee_number}: {self.get_exception_type_display()} ({status})"
