"""C6 mandatory-training compliance derivation (design spec
docs/superpowers/specs/2026-08-25-mandatory-training-compliance-design.md
§6). Compliance is derived on read, never stored -- same philosophy as
establishment.Position.current_occupant/is_vacant: no snapshot table to
keep in sync, so a new/edited CourseRequirement applies retroactively to
everyone already in scope with no backfill step.

Two entry points share this module's one core loop (`_statuses_for`) so
the logic exists once, not duplicated per caller:

* `compliance_for_employee` -- one employee's full status list (manager/
  self detail view, and the data-quality handler).
* `compliance_matrix` -- an aggregate rollup across a queryset of
  employees, by course and by department/occupational-level (the
  hr_admin dashboard).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Max
from django.utils import timezone

from core_hr.models import Employee

from .models import CourseRequirement, TrainingRecord


@dataclass
class ComplianceStatus:
    employee_id: int
    requirement_id: int
    course_id: int
    course_name: str
    status: str  # "compliant" | "due" | "overdue"
    due_date: date
    completed_on: date | None = None
    # Captured from the employee's current_version at the same moment
    # _statuses_for already fetches it (once per employee, not re-fetched
    # per caller) -- callers building a by-department/by-occupational-
    # level breakdown (the dashboard) read these instead of re-deriving
    # current_version themselves.
    department_name: str = ""
    occupational_level_name: str = ""


def _active_requirements(as_of: date):
    return (
        CourseRequirement.objects.filter(active=True, effective_from__lte=as_of, course__active=True)
        .select_related("course", "department", "occupational_level")
    )


def _requirement_applies(requirement: CourseRequirement, version) -> bool:
    if requirement.department_id is not None and requirement.department_id != version.department_id:
        return False
    if requirement.occupational_level_id is not None and requirement.occupational_level_id != version.occupational_level_id:
        return False
    return True


def _latest_completions(employee_ids, course_ids) -> dict[tuple[int, int], date]:
    """One batched query for every (employee, course) pair in scope --
    not one query per employee (this is exactly the kind of aggregating
    endpoint that N+1-queries badly otherwise)."""
    if not employee_ids or not course_ids:
        return {}
    rows = (
        TrainingRecord.objects.filter(
            employee_id__in=employee_ids, course_id__in=course_ids,
            status=TrainingRecord.Status.COMPLETED, completion_date__isnull=False,
        )
        .values("employee_id", "course_id")
        .annotate(latest=Max("completion_date"))
    )
    return {(row["employee_id"], row["course_id"]): row["latest"] for row in rows}


def _statuses_for(employees, as_of: date) -> list[ComplianceStatus]:
    employees = list(employees)
    requirements = list(_active_requirements(as_of))
    if not employees or not requirements:
        return []

    course_ids = {r.course_id for r in requirements}
    employee_ids = [e.id for e in employees]
    completions = _latest_completions(employee_ids, course_ids)

    results: list[ComplianceStatus] = []
    for employee in employees:
        version = employee.current_version
        if version is None:
            continue  # flagged separately by core_hr's own ORPHAN_RECORD check
        for requirement in requirements:
            if not _requirement_applies(requirement, version):
                continue
            subject_since = max(requirement.effective_from, version.valid_from)
            latest_completion = completions.get((employee.id, requirement.course_id))

            if latest_completion is None:
                due_date = subject_since + timedelta(days=requirement.due_within_days)
                status = "due" if as_of < due_date else "overdue"
            elif requirement.course.validity_days is None:
                due_date = latest_completion  # informational only; never lapses
                status = "compliant"
            else:
                due_date = latest_completion + timedelta(days=requirement.course.validity_days)
                status = "compliant" if as_of < due_date else "overdue"

            results.append(
                ComplianceStatus(
                    employee_id=employee.id,
                    requirement_id=requirement.id,
                    course_id=requirement.course_id,
                    course_name=requirement.course.name,
                    status=status,
                    due_date=due_date,
                    completed_on=latest_completion,
                    department_name=version.department.name,
                    occupational_level_name=version.occupational_level.name,
                )
            )
    return results


def compliance_for_employee(employee: Employee, *, as_of: date | None = None) -> list[ComplianceStatus]:
    as_of = as_of or timezone.localdate()
    return _statuses_for([employee], as_of)


def compliance_matrix(employees_qs, *, as_of: date | None = None) -> list[ComplianceStatus]:
    """The raw per-employee-per-requirement status list for a queryset of
    employees -- callers (the dashboard view, the data-quality handler)
    aggregate/filter this shared list rather than each re-deriving it.

    `Employee.current_version` is a computed property (a fresh query per
    call, not a real relation -- core_hr/models.py's own
    `version_as_at`), so this has the same per-employee version lookup
    cost `skills_inventory`/`team_development`/`wsp_atr_export` already
    each accept for the identical reason; nothing here regresses that."""
    as_of = as_of or timezone.localdate()
    return _statuses_for(employees_qs, as_of)
