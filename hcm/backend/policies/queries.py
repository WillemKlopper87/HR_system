from __future__ import annotations

# Architecture-Design.md §4's read-only cross-app seam pattern (see
# learning/queries.py for the original example). Added for the role-
# adaptive overview dashboard (core_hr.views_overview).

from core_hr.models import Employee

from .models import Policy, PolicyAcknowledgment


def policy_acknowledgment_summary() -> dict:
    """Org-wide average acknowledgment rate across every currently-
    published policy, plus the per-policy rows -- the same "internal-
    tier, no suppression" reasoning as
    policies.dashboards.acknowledgment_dashboard (which this mirrors
    rather than re-derives from a different query shape)."""
    total_active = sum(1 for e in Employee.objects.all() if e.current_version is not None)

    rows = []
    for policy in Policy.objects.filter(status=Policy.Status.PUBLISHED).order_by("title"):
        acknowledged_count = PolicyAcknowledgment.objects.filter(policy=policy).count()
        pct = round(acknowledged_count / total_active * 100, 1) if total_active else 0.0
        rows.append({"title": f"{policy.title} v{policy.version}", "acknowledged_pct": pct})

    avg_pct = round(sum(row["acknowledged_pct"] for row in rows) / len(rows), 1) if rows else None
    return {"policies": rows, "average_acknowledged_pct": avg_pct}
