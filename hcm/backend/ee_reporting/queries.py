from __future__ import annotations

# Architecture-Design.md §4's read-only cross-app seam pattern
# (learning/queries.py was the first; performance/queries.py the second,
# for C6 succession planning). ee_reporting had no read seam before this —
# added for the C6 total-rewards statement (design spec 2026-08-26 §4):
# compensation needs "this employee's current actual salary," and per
# ADR-006 / compensation.PayBand's own docstring ("actual pay stays in
# SAP"), that fact lives here, not in compensation's own models.

from rbac_audit.aggregates import suppress_count

from .aggregation import workforce_profile_matrix
from .constants import DEMOGRAPHIC_COLUMNS, OCCUPATIONAL_LEVEL_CODES
from .models import RemunerationRecord

_LEVEL_LABELS = {
    "TOP": "Top management", "SENIOR": "Senior management", "PQ": "Professionally qualified",
    "SKILLED": "Skilled technical", "SEMI": "Semi-skilled", "UNSKILLED": "Unskilled",
}


def latest_remuneration_for_employee(employee_id: int) -> dict | None:
    """The most recent RemunerationRecord for this employee, by period_end
    (not period_start — the record whose coverage ends latest is the
    better proxy for "current" than the one that started most recently,
    in case of irregular/overlapping import periods), or None if no
    record has ever been imported for them (e.g. a new hire before the
    first SAP extract). Read-only context: never an input to any stored
    value, and never treated as interchangeable with a CompProposal
    (spec §4 — a proposal is an intended change, this is the payroll
    fact)."""
    record = (
        RemunerationRecord.objects.filter(employee_id=employee_id).order_by("-period_end").first()
    )
    if record is None:
        return None
    return {
        "fixed_remuneration": record.fixed_remuneration,
        "variable_remuneration": record.variable_remuneration,
        "total_remuneration": record.total_remuneration,
        "period_start": record.period_start,
        "period_end": record.period_end,
    }


def workforce_profile_totals_by_level(as_of_date, *, suppress: bool) -> list[dict]:
    """Headcount per occupational level, as at a date -- a condensed
    preview for the role-adaptive overview dashboard
    (core_hr.views_overview), not a re-implementation of the full EEA2
    Section B matrix EquityDashboardPage already renders in full; the
    overview links there rather than duplicating every demographic
    column. Same small-cell suppression policy as everywhere else
    (RBAC-Roles.md standing rule 1) -- the caller decides whether the
    viewer's role/tier grant earns unsuppressed counts, this just applies
    that decision."""
    matrix = workforce_profile_matrix(as_of_date)
    return [
        {
            # "key" is already the human-readable label, not the raw level
            # code -- matches api/types.ts's BreakdownRow shape (key/count/
            # suppressed) so the frontend can reuse the existing
            # <Breakdown> component with no labels map needed, same as
            # core_hr.headcount_dashboard's own by_department/
            # by_occupational_level rows already do.
            "key": _LEVEL_LABELS[level_code],
            "count": suppress_count(sum(matrix[level_code][col] for col in DEMOGRAPHIC_COLUMNS), suppress=suppress),
        }
        for level_code in OCCUPATIONAL_LEVEL_CODES
    ]
