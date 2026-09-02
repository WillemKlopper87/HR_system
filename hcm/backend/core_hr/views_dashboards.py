"""Org-wide headcount dashboard. Split out of views.py (HR_Code_report.md
M5) -- no behavior change. The probation and exit-interview dashboards
live alongside their respective viewsets (views_probation.py,
views_exit_interviews.py) instead of here, keeping each dashboard
co-located with the workflow it reports on; this one covers the whole
workforce so it has no single workflow module to sit next to."""
from __future__ import annotations

from django.db.models import Count
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.aggregates import SMALL_CELL_THRESHOLD, suppress_count
from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import can_see_unsuppressed_aggregates
from rbac_audit.tiers import FieldTier
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import EmployeeVersion


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def headcount_dashboard(request):
    """Sprint 3's basic org-wide headcount dashboard. Breakdowns reuse the
    same field-tier grants as everywhere else: a role without Sensitive-tier
    read gets small-cell-suppressed counts on demographic breakdowns
    (RBAC-Roles.md standing rule 1 / gap C6), not the full RBAC field
    machinery, since these are aggregates rather than individual records."""
    employee = get_request_employee(request)
    can_see_unsuppressed = can_see_unsuppressed_aggregates(employee, FieldTier.SENSITIVE)

    current_versions = EmployeeVersion.objects.current().select_related(
        "department", "occupational_level", "job_grade"
    )

    def _breakdown(group_field: str, *, suppress: bool):
        rows = current_versions.values(group_field).annotate(count=Count("id")).order_by(group_field)
        result = []
        for row in rows:
            key = row[group_field]
            if key is None:
                continue
            count = row["count"]
            is_small = suppress and 0 < count < SMALL_CELL_THRESHOLD
            result.append({
                "key": key,
                "count": suppress_count(count, suppress=suppress),
                "suppressed": is_small,
            })
        return result

    data = {
        "total_headcount": current_versions.count(),
        "small_cell_suppression_applied": not can_see_unsuppressed,
        "by_department": _breakdown("department__name", suppress=False),
        "by_occupational_level": _breakdown("occupational_level__name", suppress=False),
        "by_job_grade": _breakdown("job_grade__name", suppress=False),
        "by_race": _breakdown("race", suppress=not can_see_unsuppressed),
        "by_gender": _breakdown("gender", suppress=not can_see_unsuppressed),
        "by_disability_status": _breakdown("disability_status", suppress=not can_see_unsuppressed),
    }
    return Response(data)
