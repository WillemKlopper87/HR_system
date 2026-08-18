"""Identity mapping between the HCM and the collab platform (ADR-011).

Employees map by **work email** (both systems hold it); departments map by
**name** (case-insensitive) — a shared IdP subject would be better and is the
C3 follow-up. Results land in `Employee.collab_user_id` /
`Department.collab_department_id`; unmatched rows are left blank and reported,
never guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core_hr.models import Department, Employee

from .collab import CollabClient


@dataclass
class SyncResult:
    employees_matched: int = 0
    employees_unmatched: list[str] = field(default_factory=list)
    departments_matched: int = 0
    departments_unmatched: list[str] = field(default_factory=list)
    dry_run: bool = False


def sync_collab_ids(client: CollabClient, *, dry_run: bool = False, only_missing: bool = True) -> SyncResult:
    result = SyncResult(dry_run=dry_run)

    collab_departments = {d["name"].strip().lower(): str(d["id"]) for d in client.list_departments() if d.get("name")}
    departments = Department.objects.filter(active=True)
    if only_missing:
        departments = departments.filter(collab_department_id="")
    for dept in departments:
        match = collab_departments.get(dept.name.strip().lower())
        if match is None:
            result.departments_unmatched.append(dept.name)
            continue
        result.departments_matched += 1
        if not dry_run:
            Department.objects.filter(pk=dept.pk).update(collab_department_id=match)

    employees = Employee.objects.exclude(work_email="")
    if only_missing:
        employees = employees.filter(collab_user_id="")
    for emp in employees.iterator():
        user_id = client.lookup_user_id(emp.work_email)
        if user_id is None:
            result.employees_unmatched.append(emp.work_email)
            continue
        result.employees_matched += 1
        if not dry_run:
            Employee.objects.filter(pk=emp.pk).update(collab_user_id=user_id)
    return result
