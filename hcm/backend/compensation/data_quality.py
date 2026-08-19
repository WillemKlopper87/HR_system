"""Data-quality handler for stale compensation proposals (H3 org-wide
sweep). Registered from `CompensationConfig.ready()`; executed by
`core_hr.data_quality.run_data_quality_checks`. A proposal is created
directly in `PROPOSED` status and only ever leaves it once (approved or
rejected) -- so `created_at` doubles as "proposed_at" and this only needs
to look at proposals still sitting in `PROPOSED`."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from .models import CompProposal

STALE_AFTER_DAYS = 14


def stale_proposal_handler():
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
