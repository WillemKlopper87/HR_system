from __future__ import annotations

import csv

from core_hr.models import Employee
from core_hr.permissions import IsHRAdmin, IsHRAdminOrReadOnly
from django.db.models import Q
from django.http import HttpResponse
from rbac_audit.drf import RowScopePermission, get_request_employee, row_scoped_queryset
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Certification, EmployeeSkill, Skill, TrainingRecord
from .serializers import CertificationSerializer, EmployeeSkillSerializer, SkillSerializer, TrainingRecordSerializer


class SkillViewSet(viewsets.ModelViewSet):
    """The skill catalog is Public-tier and read-open to everyone (needed
    for dropdowns); only hr_admin manages the catalog itself."""

    queryset = Skill.objects.all()
    serializer_class = SkillSerializer
    permission_classes = [IsHRAdminOrReadOnly]


class _RowScopedLearningViewSet(viewsets.ModelViewSet):
    """Shared list/retrieve row-scoping + ?employee= filter for the three
    per-employee learning records — same pattern as performance.Goal."""

    model = None  # set by subclasses
    select_related_fields: tuple[str, ...] = ("employee",)

    def get_queryset(self):
        queryset = self.model.objects.select_related(*self.select_related_fields)
        target_id = self.request.query_params.get("employee")
        if target_id:
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


@api_view(["GET"])
@permission_classes([IsHRAdmin])
def wsp_atr_export(request):
    """Documentation-Review-and-Gap-Analysis.md gap C2 (P1): "Skills
    Development Act reporting (WSP/ATR to SETA, due 30 April annually)
    absent from L&D sprints... add WSP/ATR export to Sprints 8-9 or it
    will be rebuilt in spreadsheets." A CSV in the shape a WSP/ATR
    submission needs — training data joined to the EEA demographic/level
    fields SETA reporting requires alongside it."""
    year = request.query_params.get("year")
    records = TrainingRecord.objects.select_related("employee").order_by("employee__employee_number")
    if year:
        records = records.filter(Q(completion_date__year=year) | Q(start_date__year=year))

    filename = f"wsp-atr-export{f'-{year}' if year else ''}.csv"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([
        "employee_number", "occupational_level", "race", "gender", "disability_status",
        "training_title", "provider", "status", "start_date", "completion_date", "hours", "cost",
    ])
    for record in records:
        version = record.employee.current_version
        writer.writerow([
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
    return response
