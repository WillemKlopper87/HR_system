from __future__ import annotations

# Architecture-Design.md §4's read-only cross-app seam pattern
# (learning/queries.py was the first; performance/queries.py the second,
# for C6 succession planning). ee_reporting had no read seam before this —
# added for the C6 total-rewards statement (design spec 2026-08-26 §4):
# compensation needs "this employee's current actual salary," and per
# ADR-006 / compensation.PayBand's own docstring ("actual pay stays in
# SAP"), that fact lives here, not in compensation's own models.

from .models import RemunerationRecord


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
