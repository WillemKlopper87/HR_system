from __future__ import annotations

from .models import TrainingRecord

# Architecture-Design.md §4: "e.g., ee_reporting reads recruitment data
# via a defined query interface in recruitment/queries.py, not by
# reaching into its models ad hoc." This is that interface for learning —
# ee_reporting's Section D (Skills Development) is the first real caller.


def employee_ids_with_completed_training_in_period(period_start, period_end) -> set[int]:
    """Distinct employees with at least one COMPLETED training record
    whose completion_date falls within [period_start, period_end] —
    EEA2 Section D counts employees trained, not training instances."""
    return set(
        TrainingRecord.objects.filter(
            status=TrainingRecord.Status.COMPLETED,
            completion_date__gte=period_start,
            completion_date__lte=period_end,
        ).values_list("employee_id", flat=True)
    )
