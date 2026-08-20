"""Org-wide data-quality sweep (H3 — Sprint 1's `run_data_quality_checks`
generalized beyond core_hr's own models, the same way retention execution
generalized in H1). Two kinds of check:

* **Built-in** — core_hr's own checks (orphan record, missing grade,
  missing demographics, and — since C1 part 2 — missing contract end
  date), inline below since they own the model.
* **Registered** — every other app's checks, registered from that app's
  own `AppConfig.ready()` via `register(exception_type, handler)`, the
  same registry shape as `rbac_audit/retention.py`. This module never
  imports a peer app (README module rule); it only dispatches by the
  `DataQualityException.ExceptionType` the handler was registered under.

Handler contract::

    def handler() -> Iterable[tuple[Employee, str]]:
        '''Yield (employee, detail) for every employee currently open for
        this exception type. Called fresh on every run -- the handler
        computes current state, it does not track deltas itself.'''

Reconciliation (open new, auto-resolve stale) is identical for built-in
and registered checks: run every handler, union what's currently
detected, resolve any open exception no longer in that set.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterable

from django.db import transaction
from django.utils import timezone

from .models import DataQualityException, Employee, EmployeeVersion

Handler = Callable[[], Iterable[tuple[Employee, str]]]
_HANDLERS: dict[str, Handler] = {}


def register(exception_type: str, handler: Handler) -> None:
    """Register (or replace) the handler for one `ExceptionType` value."""
    _HANDLERS[exception_type] = handler


def unregister(exception_type: str) -> None:
    _HANDLERS.pop(exception_type, None)


def get_handler(exception_type: str) -> Handler | None:
    return _HANDLERS.get(exception_type)


def registered_exception_types() -> list[str]:
    return sorted(_HANDLERS)


@contextmanager
def temporary_handler(exception_type: str, handler: Handler):
    """Test helper: register for the duration of a `with` block, restoring
    whatever was there before (mirrors `rbac_audit.retention.temporary_handler`)."""
    previous = _HANDLERS.get(exception_type)
    _HANDLERS[exception_type] = handler
    try:
        yield
    finally:
        if previous is None:
            _HANDLERS.pop(exception_type, None)
        else:
            _HANDLERS[exception_type] = previous


def _builtin_core_hr_checks() -> Iterable[tuple[Employee, str, str]]:
    """core_hr's four built-in checks — inline, not registered, since
    core_hr owns DataQualityException itself. Three came from Sprint 1
    (orphan record, missing grade, missing demographics); C1 part 2 added
    MISSING_CONTRACT_END_DATE, which is the whole migration-safety story
    for fixed-term employees already in service when it shipped (design
    spec §7: no backfill migration, surfaced by this check instead)."""
    for employee in Employee.objects.all():
        current = employee.current_version
        if current is None:
            yield (
                employee, DataQualityException.ExceptionType.ORPHAN_RECORD,
                "Employee has no current EmployeeVersion (no hire recorded, or coverage lapsed).",
            )
            continue

        if current.job_grade_id is None:
            yield employee, DataQualityException.ExceptionType.MISSING_GRADE, "Current version has no job_grade assigned."

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
            yield (
                employee, DataQualityException.ExceptionType.MISSING_DEMOGRAPHICS,
                f"Not disclosed: {', '.join(missing_demo)}.",
            )

        if current.employment_status == EmployeeVersion.EmploymentStatus.FIXED_TERM and current.contract_end_date is None:
            yield (
                employee, DataQualityException.ExceptionType.MISSING_CONTRACT_END_DATE,
                "Fixed-term employee has no contract end date recorded.",
            )


@transaction.atomic
def run_data_quality_checks() -> dict[str, int]:
    """Runs the built-in checks plus every registered handler, opens/updates
    `DataQualityException` rows for what's currently detected, and
    auto-resolves any open exception that's no longer found — org-wide,
    not just core_hr, as of H3. A handler that raises is isolated and
    skipped (one broken check must not block every other module's)."""
    detected: set[tuple[int, str]] = set()

    for employee, exception_type, detail in _builtin_core_hr_checks():
        _flag(detected, employee, exception_type, detail)

    for exception_type, handler in _HANDLERS.items():
        try:
            for employee, detail in handler():
                _flag(detected, employee, exception_type, detail)
        except Exception:  # noqa: BLE001 — isolate per handler, keep sweeping
            import logging

            logging.getLogger(__name__).exception(
                "data_quality: handler for %s failed", exception_type
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
