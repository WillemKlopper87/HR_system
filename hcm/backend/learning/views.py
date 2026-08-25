from __future__ import annotations

import csv
from collections import defaultdict

from core_hr.models import Employee
from core_hr.permissions import IsHRAdmin, IsHRAdminOrReadOnly
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.drf import RowScopePermission, get_request_employee, int_query_param, row_scoped_queryset
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .compliance import compliance_matrix
from .models import Certification, Course, CourseRequirement, EmployeeSkill, Skill, TrainingRecord
from .serializers import (
    CertificationSerializer,
    CourseRequirementSerializer,
    CourseSerializer,
    EmployeeSkillSerializer,
    SkillSerializer,
    TrainingRecordSerializer,
)


class SkillViewSet(viewsets.ModelViewSet):
    """The skill catalog is Public-tier and read-open to everyone (needed
    for dropdowns); only hr_admin manages the catalog itself."""

    queryset = Skill.objects.all()
    serializer_class = SkillSerializer
    permission_classes = [IsHRAdminOrReadOnly]


class CourseViewSet(viewsets.ModelViewSet):
    """The course catalogue -- same shape/reasoning as SkillViewSet:
    Public tier, read-open to everyone (dropdowns, and so a manager can
    see what a report's overdue item actually is), hr_admin manages it."""

    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [IsHRAdminOrReadOnly]


class CourseRequirementViewSet(viewsets.ModelViewSet):
    """'Required for role' rules (design spec §2.3/§5.1) -- same
    read-open/hr_admin-write shape as CourseViewSet; validation (a
    requirement must target a mandatory course, no duplicate active
    scope) lives in CourseRequirementSerializer."""

    queryset = CourseRequirement.objects.select_related("course", "department", "occupational_level")
    serializer_class = CourseRequirementSerializer
    permission_classes = [IsHRAdminOrReadOnly]


class _RowScopedLearningViewSet(viewsets.ModelViewSet):
    """Shared list/retrieve row-scoping + ?employee= filter for the three
    per-employee learning records — same pattern as performance.Goal."""

    model = None  # set by subclasses
    select_related_fields: tuple[str, ...] = ("employee",)

    def get_queryset(self):
        queryset = self.model.objects.select_related(*self.select_related_fields)
        target_id = int_query_param(self.request, "employee")
        if target_id is not None:
            queryset = queryset.filter(employee_id=target_id)
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        return row_scoped_queryset(queryset, employee)

    def get_target_employee(self, obj):
        return obj.employee


class EmployeeSkillViewSet(_RowScopedLearningViewSet):
    model = EmployeeSkill
    select_related_fields = ("employee", "skill")
    serializer_class = EmployeeSkillSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]


class CertificationViewSet(_RowScopedLearningViewSet):
    model = Certification
    serializer_class = CertificationSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]


class TrainingRecordViewSet(_RowScopedLearningViewSet):
    model = TrainingRecord
    serializer_class = TrainingRecordSerializer
    permission_classes = [permissions.IsAuthenticated, RowScopePermission]


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsHRAdmin])
def skills_inventory(request):
    """Sprint 8 task: "org-wide skills inventory report (gap analysis by
    department/level)". Skill possession is Internal-tier, not Sensitive
    (Data-Dictionary.md), so no small-cell suppression applies here —
    that rule targets demographic aggregates specifically (gap C6)."""
    skills = []
    for skill in Skill.objects.filter(active=True):
        holders = EmployeeSkill.objects.filter(skill=skill).select_related("employee")
        by_department: dict[str, int] = {}
        by_level: dict[str, int] = {}
        total = 0
        for holder in holders:
            version = holder.employee.current_version
            if version is None:
                continue
            total += 1
            by_department[version.department.name] = by_department.get(version.department.name, 0) + 1
            by_level[version.occupational_level.name] = by_level.get(version.occupational_level.name, 0) + 1
        skills.append({
            "skill": skill.name,
            "category": skill.category,
            "total_holders": total,
            "by_department": [{"key": k, "count": v} for k, v in sorted(by_department.items())],
            "by_occupational_level": [{"key": k, "count": v} for k, v in sorted(by_level.items())],
        })

    return Response({"skills": skills})


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def team_development(request):
    """Sprint 8 task: "manager view of team development plans" — a
    per-employee rollup (skills/certifications/training counts) across
    whatever the requester's row-scope covers (their team, or everyone
    for hr_admin), reusing the same row-scope infrastructure as every
    other module rather than building bespoke access control."""
    employee = get_request_employee(request)
    employees = row_scoped_queryset(Employee.objects.all(), employee, employee_field=None)

    rows = []
    for emp in employees:
        rows.append({
            "employee": emp.id,
            "employee_number": emp.employee_number,
            "name": f"{emp.first_name} {emp.last_name}",
            "skill_count": EmployeeSkill.objects.filter(employee=emp).count(),
            "certification_count": Certification.objects.filter(employee=emp).count(),
            "active_training_count": TrainingRecord.objects.filter(
                employee=emp, status__in=[TrainingRecord.Status.PLANNED, TrainingRecord.Status.IN_PROGRESS]
            ).count(),
            "completed_training_count": TrainingRecord.objects.filter(
                employee=emp, status=TrainingRecord.Status.COMPLETED
            ).count(),
        })
    return Response({"employees": rows})


@extend_schema(responses={200: OpenApiTypes.BINARY})
@api_view(["GET"])
@permission_classes([IsHRAdmin])
def wsp_atr_export(request):
    """Documentation-Review-and-Gap-Analysis.md gap C2 (P1): "Skills
    Development Act reporting (WSP/ATR to SETA, due 30 April annually)
    absent from L&D sprints... add WSP/ATR export to Sprints 8-9 or it
    will be rebuilt in spreadsheets." A CSV in the shape a WSP/ATR
    submission needs — training data joined to the EEA demographic/level
    fields SETA reporting requires alongside it.

    C2 (docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md
    §2.4): also unions in Certification rows via a `record_type` column —
    qualifications feed WSP/ATR too, and Certification wasn't in this
    export at all before this. Purely additive within this app (it already
    owns both models); no new peer-app coupling. Qualification rows carry
    name/issuing_body in the training_title/provider columns (same shape,
    different semantic label) with hours/cost/status/completion_date left
    blank — concepts that don't apply to a qualification."""
    year = int_query_param(request, "year")
    training_records = TrainingRecord.objects.select_related("employee").order_by("employee__employee_number")
    certifications = Certification.objects.select_related("employee").order_by("employee__employee_number")
    if year is not None:
        training_records = training_records.filter(Q(completion_date__year=year) | Q(start_date__year=year))
        certifications = certifications.filter(issue_date__year=year)

    filename = f"wsp-atr-export{f'-{year}' if year else ''}.csv"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([
        "record_type", "employee_number", "occupational_level", "race", "gender", "disability_status",
        "training_title", "provider", "status", "start_date", "completion_date", "hours", "cost",
    ])
    for record in training_records:
        version = record.employee.current_version
        writer.writerow([
            "training",
            record.employee.employee_number,
            version.occupational_level.name if version else "",
            version.race if version else "",
            version.gender if version else "",
            version.disability_status if version else "",
            record.title,
            record.provider,
            record.status,
            record.start_date or "",
            record.completion_date or "",
            record.hours if record.hours is not None else "",
            record.cost if record.cost is not None else "",
        ])
    for cert in certifications:
        version = cert.employee.current_version
        writer.writerow([
            "qualification",
            cert.employee.employee_number,
            version.occupational_level.name if version else "",
            version.race if version else "",
            version.gender if version else "",
            version.disability_status if version else "",
            cert.name,
            cert.issuing_body,
            "",
            cert.issue_date or "",
            "",
            "",
            "",
        ])
    return response


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsHRAdmin])
def training_compliance_dashboard(request):
    """C6 design spec §5.3: aggregate completion-rate rollup by mandatory
    course, org-wide and by department/occupational level. hr_admin only
    -- same gate and no-suppression reasoning as skills_inventory
    (Internal-tier subject matter, already restricted to hr_admin, so
    small-cell suppression -- which protects a *wider* audience from
    demographic aggregates -- has no audience to protect against here).
    The named overdue-individuals list is a separate, row-scoped endpoint
    (training_compliance_overdue) -- this one never names anyone."""
    today = timezone.localdate()
    statuses = compliance_matrix(Employee.objects.all(), as_of=today)

    courses: dict[int, dict] = {}
    for status in statuses:
        entry = courses.setdefault(status.course_id, {
            "course": status.course_id,
            "name": status.course_name,
            "total_subject": 0,
            "compliant": 0,
            "due": 0,
            "overdue": 0,
            "_by_department": defaultdict(lambda: {"total_subject": 0, "compliant": 0, "due": 0, "overdue": 0}),
            "_by_occupational_level": defaultdict(lambda: {"total_subject": 0, "compliant": 0, "due": 0, "overdue": 0}),
        })
        entry["total_subject"] += 1
        entry[status.status] += 1
        for bucket_key, bucket_name in (
            ("_by_department", status.department_name), ("_by_occupational_level", status.occupational_level_name),
        ):
            bucket = entry[bucket_key][bucket_name]
            bucket["total_subject"] += 1
            bucket[status.status] += 1

    course_rows = []
    for entry in courses.values():
        total = entry["total_subject"]
        course_rows.append({
            "course": entry["course"],
            "name": entry["name"],
            "total_subject": total,
            "compliant": entry["compliant"],
            "due": entry["due"],
            "overdue": entry["overdue"],
            "completion_rate_pct": round(entry["compliant"] / total * 100, 1) if total else None,
            "by_department": [
                {"key": key, **counts} for key, counts in sorted(entry["_by_department"].items())
            ],
            "by_occupational_level": [
                {"key": key, **counts} for key, counts in sorted(entry["_by_occupational_level"].items())
            ],
        })
    course_rows.sort(key=lambda row: row["name"])

    return Response({"as_of": today, "courses": course_rows})


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def training_compliance_overdue(request):
    """C6 design spec §5.4: the named overdue-individuals list, row-scoped
    exactly like `team_development` -- hr_admin/auditor/other all-scope
    roles see everyone, line_manager sees only their own reporting chain,
    a base employee sees only themselves. No new access-control mechanism
    invented; small-cell suppression doesn't apply here (this list is
    already scoped to people the requester has a legitimate operational
    reason to see individually, not a demographic aggregate)."""
    today = timezone.localdate()
    employee = get_request_employee(request)
    employees = list(row_scoped_queryset(Employee.objects.all(), employee, employee_field=None))
    statuses = compliance_matrix(employees, as_of=today)

    employees_by_id = {e.id: e for e in employees}
    rows = []
    for status in statuses:
        if status.status != "overdue":
            continue
        emp = employees_by_id.get(status.employee_id)
        if emp is None:
            continue
        rows.append({
            "employee": emp.id,
            "employee_number": emp.employee_number,
            "name": f"{emp.first_name} {emp.last_name}",
            "course": status.course_id,
            "course_name": status.course_name,
            "due_date": status.due_date,
            "days_overdue": (today - status.due_date).days,
        })
    rows.sort(key=lambda r: (-r["days_overdue"], r["employee_number"]))
    return Response({"overdue": rows})
