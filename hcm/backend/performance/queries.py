from __future__ import annotations

# Architecture-Design.md §4's read-only cross-app seam pattern
# (learning/queries.py was the first; this is performance's own, added for
# C6 succession planning -- spec docs/superpowers/specs/2026-08-25-
# succession-talent-pools-design.md §2.7). No prior caller needed one.

from .models.agreements import PerformanceAgreement


def latest_final_score(employee_id: int) -> dict | None:
    """Most recent PerformanceAgreement with a frozen final_score for this
    employee (set once the Head signs the FINAL stage —
    performance/services/agreements.py::_finalize_scoring), or None if the
    employee has no scored agreement yet. Read-only context for succession
    readiness (informational only — never an input to the stored readiness
    value, which stays a human judgement call)."""
    agreement = (
        PerformanceAgreement.objects.filter(employee_id=employee_id, final_score__isnull=False)
        .select_related("period")
        .order_by("-period__start_date")
        .first()
    )
    if agreement is None:
        return None
    return {
        "final_score": agreement.final_score,
        "period_name": agreement.period.name,
        "hr_attention": agreement.hr_attention,
    }
