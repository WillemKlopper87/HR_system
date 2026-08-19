from __future__ import annotations

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import can_see_unsuppressed_aggregates
from rbac_audit.tiers import FieldTier
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import aggregation
from .constants import AGGREGATE_ROW_KEYS, DEMOGRAPHIC_COLUMNS, OCCUPATIONAL_LEVEL_CODES
from .models import EEPlan

SMALL_CELL_THRESHOLD = 5


def _suppress_matrix(matrix: dict, *, suppress: bool) -> dict:
    """Same small-cell-suppression rule as core_hr's headcount dashboard
    (RBAC-Roles.md standing rule 1 / gap C6), applied per cell rather
    than per breakdown row, since this is a full level x demographic
    matrix, not a single-dimension list."""
    if not suppress:
        return matrix
    return {
        row: {
            col: (f"<{SMALL_CELL_THRESHOLD}" if 0 < value < SMALL_CELL_THRESHOLD else value)
            for col, value in cols.items()
        }
        for row, cols in matrix.items()
    }


def _target_gap(actual: dict, targets: dict) -> dict:
    """Per level x column, actual minus target — target data is % of
    workforce (EEPlan.annual_targets), so this reports the gap in
    percentage points against the actual matrix's own row total, not a
    headcount gap. Absent target cells are omitted (no target set)."""
    gap = {}
    for row in OCCUPATIONAL_LEVEL_CODES + AGGREGATE_ROW_KEYS:
        row_actual = actual.get(row, {})
        row_target = targets.get(row, {})
        row_total = sum(v for v in row_actual.values() if isinstance(v, (int, float))) or None
        row_gap = {}
        for col in DEMOGRAPHIC_COLUMNS:
            if col not in row_target:
                continue
            actual_value = row_actual.get(col, 0)
            actual_pct = round((actual_value / row_total) * 100, 1) if row_total else 0
            row_gap[col] = round(actual_pct - float(row_target[col]), 1)
        if row_gap:
            gap[row] = row_gap
    return gap


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def equity_dashboard(request):
    """Extends Sprint 3's basic headcount dashboard (core_hr/views.py::
    headcount_dashboard, which stays untouched) with the same
    level x population-group x gender matrix EEA2 Section B uses — live,
    not a frozen report snapshot — plus target-vs-actual tracking against
    the current EEPlan where one exists (sprint task: "EE target-vs-
    actual tracking (if in scope)")."""
    employee = get_request_employee(request)
    can_see_unsuppressed = can_see_unsuppressed_aggregates(employee, FieldTier.SENSITIVE)
    today = timezone.localdate()

    workforce = aggregation.workforce_profile_matrix(today)
    disability = aggregation.disability_workforce_matrix(today)

    plan = EEPlan.objects.filter(plan_period_start__lte=today, plan_period_end__gte=today).order_by("-plan_period_start").first()
    target_gap = _target_gap(workforce, plan.annual_targets) if plan and plan.annual_targets else {}

    return Response({
        "as_of": today,
        "small_cell_suppression_applied": not can_see_unsuppressed,
        "workforce_profile": _suppress_matrix(workforce, suppress=not can_see_unsuppressed),
        "disability_workforce": _suppress_matrix(disability, suppress=not can_see_unsuppressed),
        "ee_plan_id": plan.id if plan else None,
        "target_vs_actual_gap_pct": target_gap,
    })
