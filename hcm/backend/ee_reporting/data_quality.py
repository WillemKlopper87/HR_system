"""Data-quality handler for ee_reporting (H3 org-wide sweep). Registered
from `EeReportingConfig.ready()`; executed by
`core_hr.data_quality.run_data_quality_checks`."""
from __future__ import annotations

from django.utils import timezone

from .models import EEPlanMeasure


def measure_overdue_handler():
    """Design spec 2026-08-26 §4.3: a planned/in-progress affirmative-action
    measure past its EEA13 target date, attached to its responsible person.
    Composition adequacy deliberately isn't a DQ entry — it has no employee
    to hang on and is surfaced live on the forum page instead."""
    today = timezone.localdate()
    measures = (
        EEPlanMeasure.objects.filter(
            status__in=[EEPlanMeasure.Status.PLANNED, EEPlanMeasure.Status.IN_PROGRESS], target_end__lt=today,
        )
        .select_related("owner", "plan")
    )
    for measure in measures:
        yield (
            measure.owner,
            f"EE plan measure '{measure.get_category_display()}' was due {measure.target_end} and is still "
            f"{measure.get_status_display().lower()}.",
        )
