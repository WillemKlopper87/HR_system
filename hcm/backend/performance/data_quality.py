"""Data-quality handler for overdue performance stages (H3 org-wide sweep).
Registered from `PerformanceConfig.ready()`; executed by
`core_hr.data_quality.run_data_quality_checks`. Reuses `reminders.py`'s own
"who is outstanding for the open phase" logic (`outstanding_agreements`,
`open_phase_for`) rather than re-deriving it -- the reminder engine already
computes exactly this, this just adds "and it's past the deadline"."""
from __future__ import annotations

from django.utils import timezone

from .models import PerformanceAgreement, PerformancePeriod, PeriodPhase
from .reminders import open_phase_for, outstanding_agreements


def overdue_agreement_handler():
    today = timezone.localdate()
    open_statuses = [
        PerformancePeriod.Status.CONTRACTING, PerformancePeriod.Status.MIDYEAR, PerformancePeriod.Status.FINAL,
    ]
    for period in PerformancePeriod.objects.filter(status__in=open_statuses):
        phase = open_phase_for(period)
        if phase is None or phase.due_on >= today:
            continue
        days_overdue = (today - phase.due_on).days
        for agreement in outstanding_agreements(period, phase.stage):
            yield (
                agreement.employee,
                f"{period.name} {phase.get_stage_display()} overdue by {days_overdue} day(s) (due {phase.due_on}).",
            )


def missing_calibration_handler():
    """Once a period's FINAL phase due date has passed, every FINAL_SIGNED
    agreement in it should have gone through at least one calibration
    session before archive (design spec §2.12). A period-wide gap is
    surfaced per-employee -- same shape as `overdue_agreement_handler`,
    since `DataQualityException` is keyed to an employee, not a period."""
    today = timezone.localdate()
    periods = PerformancePeriod.objects.filter(
        status__in=[PerformancePeriod.Status.FINAL, PerformancePeriod.Status.CLOSED]
    ).exclude(calibration_sessions__isnull=False)
    for period in periods:
        phase = period.phase(PeriodPhase.Stage.FINAL)
        if phase is None or phase.due_on >= today:
            continue
        agreements = period.agreements.filter(
            status=PerformanceAgreement.Status.FINAL_SIGNED
        ).select_related("employee")
        for agreement in agreements:
            yield (
                agreement.employee,
                f"{period.name} final assessment signed but no calibration session has been opened yet.",
            )
