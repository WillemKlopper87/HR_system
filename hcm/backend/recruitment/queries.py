from __future__ import annotations

# Architecture-Design.md §4's read-only cross-app seam pattern (see
# learning/queries.py for the original example). Added for the role-
# adaptive overview dashboard (core_hr.views_overview).

from django.db.models import Count

from .models import Applicant, ApplicantStageEvent, Requisition


def recruitment_summary() -> dict:
    """Open requisitions, average days-to-fill, and a simple pipeline
    funnel by current stage -- org-wide, not row-scoped or small-cell
    suppressed. This mirrors recruitment.views.recruitment_dashboard's
    own open_requisitions/avg_time_to_fill_days/by_stage computation
    (kept in sync deliberately, not re-derived from a different query
    shape) but is deliberately NOT suppressed: the overview's recruiter/
    hr_admin-facing summary card, same audience recruitment_dashboard
    itself already serves unsuppressed for that audience."""
    applicants = Applicant.objects.all()
    by_stage = list(applicants.values("current_stage").annotate(count=Count("id")).order_by("current_stage"))

    hire_events = ApplicantStageEvent.objects.filter(to_stage=Applicant.Stage.HIRED).select_related(
        "applicant__requisition"
    )
    fill_days = [
        (event.created_at.date() - event.applicant.requisition.opened_at).days
        for event in hire_events
        if event.applicant.requisition.opened_at is not None
    ]
    avg_days_to_fill = round(sum(fill_days) / len(fill_days), 1) if fill_days else None

    return {
        "open_requisitions": Requisition.objects.filter(status=Requisition.Status.OPEN).count(),
        "avg_days_to_fill": avg_days_to_fill,
        "by_stage": [{"key": row["current_stage"], "count": row["count"]} for row in by_stage],
    }
