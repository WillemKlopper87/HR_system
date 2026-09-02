from __future__ import annotations

# Architecture-Design.md §4's read-only cross-app seam pattern (see
# learning/queries.py for the original example). Added for the role-
# adaptive overview dashboard (core_hr.views_overview), which needs a
# funded/filled/vacancy summary without importing establishment.models
# directly.

from .models import Position


def establishment_summary() -> dict:
    """Org-wide approved-post summary. `is_vacant` is a per-instance
    property (Position.current_occupant does its own query), so this
    computes the same fact set-based instead of looping every approved
    post in Python."""
    from core_hr.models import EmployeeVersion

    approved = Position.objects.filter(status=Position.Status.APPROVED)
    funded = approved.count()
    occupied = (
        EmployeeVersion.objects.filter(valid_to__isnull=True, position__in=approved)
        .values("position_id")
        .distinct()
        .count()
    )
    vacant = funded - occupied
    return {
        "funded": funded,
        "filled": occupied,
        "vacant": vacant,
        "vacancy_rate_pct": round(vacant / funded * 100, 1) if funded else 0.0,
    }


def get_vacant_position(position_id: int):
    """Returns the Position if it is approved and currently unoccupied,
    else None. The picker itself is just GET /positions/?vacant=true
    (PositionViewSet already supports that filter); this is the matching
    write-path validation for core_hr.contracts.decide_contract_action's
    convert-to-permanent action, which cannot import establishment.models
    directly (Architecture-Design.md §4)."""
    return Position.objects.vacant().filter(id=position_id).first()
