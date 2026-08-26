"""Data-quality handlers for compensation (H3 org-wide sweep). Registered
from `CompensationConfig.ready()`; executed by
`core_hr.data_quality.run_data_quality_checks`."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import CompCycle, CompProposal

STALE_AFTER_DAYS = 14


def stale_proposal_handler():
    """A proposal is created directly in PROPOSED status and only ever
    leaves it once (approved or rejected) -- so `created_at` doubles as
    "proposed_at" and this only needs to look at proposals still sitting
    in PROPOSED."""
    cutoff = timezone.now() - timedelta(days=STALE_AFTER_DAYS)
    proposals = (
        CompProposal.objects.filter(status=CompProposal.Status.PROPOSED, created_at__lte=cutoff)
        .select_related("employee")
    )
    for proposal in proposals:
        days_open = (timezone.now() - proposal.created_at).days
        yield (
            proposal.employee,
            f"Compensation proposal for {proposal.employee} has been awaiting review for {days_open} day(s) "
            f"(proposed {proposal.created_at.date()}).",
        )


def cycle_overdue_handler():
    """Design spec 2026-08-26 §2.7 — not "exceeds cycle budget" (already a
    live flag directly on the proposal, so a data-quality exception for it
    would just be noise); this is a genuinely new signal: a review round
    whose window has closed but that still has undecided proposals in it.
    Mirrors stale_proposal_handler's exact shape, attached to the
    proposal's own employee."""
    today = timezone.localdate()
    overdue_cycles = CompCycle.objects.filter(status=CompCycle.Status.OPEN, period_end__lt=today)
    proposals = (
        CompProposal.objects.filter(cycle__in=overdue_cycles, status=CompProposal.Status.PROPOSED)
        .select_related("employee", "cycle")
    )
    for proposal in proposals:
        yield (
            proposal.employee,
            f"Compensation cycle '{proposal.cycle.name}' ended {proposal.cycle.period_end} and still has an "
            f"unresolved proposal for {proposal.employee}.",
        )
