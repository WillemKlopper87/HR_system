"""Data-quality handler for overdue mandatory training (H3 org-wide
sweep, C6). Registered from `LearningConfig.ready()`; executed by
`core_hr.data_quality.run_data_quality_checks`. Reuses
`learning.compliance`'s own derivation rather than re-deriving overdue
status -- same shape as `performance/data_quality.py::
overdue_agreement_handler` reusing `reminders.py`'s `outstanding_agreements`."""
from __future__ import annotations

from core_hr.models import Employee
from django.utils import timezone

from .compliance import compliance_matrix


def overdue_training_handler():
    today = timezone.localdate()
    employees = {e.id: e for e in Employee.objects.all()}
    statuses = compliance_matrix(Employee.objects.all(), as_of=today)
    for status in statuses:
        if status.status != "overdue":
            continue
        days_overdue = (today - status.due_date).days
        yield (
            employees[status.employee_id],
            f"{status.course_name} overdue by {days_overdue} day(s) (due {status.due_date}).",
        )
