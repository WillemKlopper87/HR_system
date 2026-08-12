from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import DataQualityException, Employee


@transaction.atomic
def run_data_quality_checks() -> dict[str, int]:
    """Detect the Sprint 1 exception categories — missing grade, missing
    demographics, orphan records — and reconcile DataQualityException rows:
    opens new exceptions and auto-resolves ones that no longer apply."""
    detected: set[tuple[int, str]] = set()

    for employee in Employee.objects.all():
        current = employee.current_version
        if current is None:
            _flag(
                detected, employee, DataQualityException.ExceptionType.ORPHAN_RECORD,
                "Employee has no current EmployeeVersion (no hire recorded, or coverage lapsed).",
            )
            continue

        if current.job_grade_id is None:
            _flag(
                detected, employee, DataQualityException.ExceptionType.MISSING_GRADE,
                "Current version has no job_grade assigned.",
            )

        missing_demo = [
            field_name
            for field_name, value in (
                ("race", current.race),
                ("gender", current.gender),
                ("disability_status", current.disability_status),
            )
            if value == "not_disclosed"
        ]
        if missing_demo:
            _flag(
                detected, employee, DataQualityException.ExceptionType.MISSING_DEMOGRAPHICS,
                f"Not disclosed: {', '.join(missing_demo)}.",
            )

    open_qs = DataQualityException.objects.filter(resolved_at__isnull=True)
    for exc in open_qs:
        if (exc.employee_id, exc.exception_type) not in detected:
            exc.resolved_at = timezone.now()
            exc.save(update_fields=["resolved_at"])

    return {"open_exceptions": DataQualityException.objects.filter(resolved_at__isnull=True).count()}


def _flag(detected: set, employee: Employee, exception_type: str, detail: str) -> None:
    detected.add((employee.id, exception_type))
    DataQualityException.objects.update_or_create(
        employee=employee,
        exception_type=exception_type,
        resolved_at=None,
        defaults={"detail": detail},
    )
