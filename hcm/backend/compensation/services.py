from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from ee_reporting.queries import latest_remuneration_for_employee
from notifications.services import notify

from .models import CompCycle, CompProposal, PayBand


class ApprovalError(ValueError):
    pass


def evaluate_requires_override(employee, proposed_salary) -> bool:
    """True if proposed_salary falls outside the CURRENT pay band for the
    employee's current job grade — or if there's no job grade / pay band
    to check against at all, which is treated conservatively as requiring
    override rather than silently waving the proposal through."""
    version = employee.current_version
    if version is None or version.job_grade_id is None:
        return True
    band = PayBand.objects.filter(job_grade=version.job_grade).current().first()
    if band is None:
        return True
    return not band.contains(proposed_salary)


def _cycle_reserved_total(cycle: CompCycle, *, exclude_id: int | None = None) -> Decimal:
    """Sum of budget_impact for every PROPOSED/APPROVED proposal against
    this cycle (REJECTED never happened, so it never counts) — a pending
    proposal provisionally reserves its share of the budget the moment
    it's raised, design spec §2.5. Call only while holding a lock on
    `cycle` (select_for_update in the caller) — this function itself does
    not lock, since it needs to run as part of a larger read-then-write
    critical section, not its own transaction."""
    qs = cycle.proposals.filter(status__in=[CompProposal.Status.PROPOSED, CompProposal.Status.APPROVED])
    if exclude_id is not None:
        qs = qs.exclude(pk=exclude_id)
    total = Decimal("0")
    for proposal in qs:
        impact = proposal.budget_impact
        if impact is not None:
            total += impact
    return total


def cycle_utilization(cycle: CompCycle) -> dict:
    """Read-only utilization summary for display (dashboards, the cycle
    list) — no lock needed here: an approximate, eventually-consistent
    number is fine for a GET, unlike the write paths below which must not
    race (design spec §2.5)."""
    committed = Decimal("0")
    pending = Decimal("0")
    for proposal in cycle.proposals.filter(
        status__in=[CompProposal.Status.PROPOSED, CompProposal.Status.APPROVED]
    ):
        impact = proposal.budget_impact
        if impact is None:
            continue
        if proposal.status == CompProposal.Status.APPROVED:
            committed += impact
        else:
            pending += impact
    total_used = committed + pending
    return {
        "committed_total": committed,
        "pending_total": pending,
        "total_used": total_used,
        "remaining": cycle.budget_amount - total_used,
        "over_budget": total_used > cycle.budget_amount,
    }


@transaction.atomic
def propose_compensation_change(
    *,
    employee,
    proposal_type: str = CompProposal.ProposalType.INCREASE,
    proposed_annual_salary=None,
    bonus_amount=None,
    cycle: CompCycle | None = None,
    justification: str = "",
    proposed_by=None,
    effective_date=None,
) -> CompProposal:
    version = employee.current_version
    if version is None or version.job_grade_id is None:
        raise ValueError("Employee has no current job grade to evaluate a compensation proposal against.")

    baseline = None
    requires_override = False
    if proposal_type == CompProposal.ProposalType.INCREASE:
        if proposed_annual_salary is None:
            raise ValueError("A salary-increase proposal requires a proposed annual salary.")
        requires_override = evaluate_requires_override(employee, proposed_annual_salary)
    elif proposal_type == CompProposal.ProposalType.BONUS:
        if bonus_amount is None:
            raise ValueError("A bonus proposal requires a bonus amount.")
    else:
        raise ValueError(f"Unknown proposal_type {proposal_type!r}.")

    exceeds_budget = False
    if cycle is not None:
        # Lock the cycle row for the duration of this transaction so a
        # concurrent create/approve against the SAME cycle can't also read
        # a stale utilization total and independently decide it's under
        # budget too (design spec §2.5 — the same select_for_update shape
        # core_hr.Employee.apply_lifecycle_event already uses for its own
        # read-then-write race).
        cycle = CompCycle.objects.select_for_update().get(pk=cycle.pk)
        if cycle.status != CompCycle.Status.OPEN:
            raise ValueError("Proposals can only be created against an open cycle.")
        if cycle.department_id is not None and version.department_id != cycle.department_id:
            raise ValueError("This employee is outside the cycle's department scope.")

        if proposal_type == CompProposal.ProposalType.INCREASE:
            baseline_data = latest_remuneration_for_employee(employee.id)
            if baseline_data is None:
                raise ValueError(
                    "Cannot attach a salary-increase proposal to a cycle: no remuneration record on file "
                    "for this employee to compute the budget impact against."
                )
            baseline = baseline_data["fixed_remuneration"]
            impact = proposed_annual_salary - baseline
        else:
            impact = bonus_amount

        reserved = _cycle_reserved_total(cycle)
        exceeds_budget = (reserved + impact) > cycle.budget_amount

    return CompProposal.objects.create(
        employee=employee,
        current_job_grade=version.job_grade,
        proposal_type=proposal_type,
        proposed_annual_salary=proposed_annual_salary if proposal_type == CompProposal.ProposalType.INCREASE else None,
        bonus_amount=bonus_amount if proposal_type == CompProposal.ProposalType.BONUS else None,
        baseline_salary_at_proposal=baseline,
        cycle=cycle,
        justification=justification,
        status=CompProposal.Status.PROPOSED,
        requires_override=requires_override,
        exceeds_cycle_budget=exceeds_budget,
        proposed_by=proposed_by,
        effective_date=effective_date,
    )


def approve_proposal(proposal: CompProposal, *, approver, override_reason: str = "") -> CompProposal:
    if proposal.status != CompProposal.Status.PROPOSED:
        raise ApprovalError("Only a proposed compensation change can be approved.")
    if approver is not None and proposal.proposed_by_id == approver.id:
        raise ApprovalError("The proposer cannot also approve this compensation change (segregation of duties).")

    needs_override_reason = proposal.requires_override
    update_fields = ["status", "approved_by", "approved_at"]

    with transaction.atomic():
        if proposal.cycle_id is not None:
            # Lock the CYCLE row (not the proposal) so a concurrent
            # create/approve against the SAME cycle can't also read a
            # stale utilization total (design spec §2.5) — re-derive
            # exceeds_cycle_budget fresh here rather than trusting the
            # value computed at proposal-creation time, since cycle
            # utilization is a shared, moving total across every proposal
            # against it. Mutates the SAME `proposal` instance the caller
            # passed in throughout (never rebound to a fresh fetch) —
            # callers (the approve view action, and tests that call this
            # service directly and then re-check `proposal.status` on
            # their own reference) rely on in-place mutation.
            cycle = CompCycle.objects.select_for_update().get(pk=proposal.cycle_id)
            reserved_excluding_this = _cycle_reserved_total(cycle, exclude_id=proposal.pk)
            impact = proposal.budget_impact or Decimal("0")
            exceeds_now = (reserved_excluding_this + impact) > cycle.budget_amount
            # Always set + persist, unconditionally — not "only if changed
            # from the in-memory value," which would wrongly skip
            # persisting a True that a PRIOR failed approve() attempt on
            # this same object already set in memory (without saving,
            # since it raised before reaching .save()) but that the DB row
            # itself never actually got.
            proposal.exceeds_cycle_budget = exceeds_now
            update_fields.append("exceeds_cycle_budget")
            needs_override_reason = needs_override_reason or exceeds_now

        if needs_override_reason and not override_reason:
            raise ApprovalError(
                "This proposal is outside the pay band and/or exceeds its cycle's budget — an override "
                "reason is required to approve it."
            )

        proposal.status = CompProposal.Status.APPROVED
        proposal.approved_by = approver
        proposal.approved_at = timezone.now()
        if override_reason:
            proposal.override_reason = override_reason
            update_fields.append("override_reason")
        proposal.save(update_fields=update_fields)

    if proposal.proposed_by_id:
        notify(
            recipient=proposal.proposed_by, kind="comp_approval",
            title=f"Compensation proposal approved for {proposal.employee.employee_number}",
            body=f"Proposed annual salary {proposal.proposed_annual_salary} was approved.",
            link="/comp-proposals",
        )
    return proposal


def reject_proposal(proposal: CompProposal, *, approver) -> CompProposal:
    if proposal.status != CompProposal.Status.PROPOSED:
        raise ApprovalError("Only a proposed compensation change can be rejected.")
    proposal.status = CompProposal.Status.REJECTED
    proposal.approved_by = approver
    proposal.approved_at = timezone.now()
    proposal.save(update_fields=["status", "approved_by", "approved_at"])
    if proposal.proposed_by_id:
        notify(
            recipient=proposal.proposed_by, kind="comp_approval",
            title=f"Compensation proposal rejected for {proposal.employee.employee_number}",
            body=f"Proposed annual salary {proposal.proposed_annual_salary} was rejected.",
            link="/comp-proposals",
        )
    return proposal


def open_cycle(cycle: CompCycle) -> CompCycle:
    if cycle.status != CompCycle.Status.DRAFT:
        raise ApprovalError("Only a draft cycle can be opened.")
    cycle.status = CompCycle.Status.OPEN
    cycle.save(update_fields=["status"])
    return cycle


@transaction.atomic
def close_cycle(cycle: CompCycle, *, actor) -> CompCycle:
    """Still-PROPOSED proposals are auto-rejected, never silently
    orphaned and never auto-approved (design spec §2.6) — committing
    money nobody explicitly approved is the wrong default; rejecting
    just means the proposer can re-raise it in a future cycle if it's
    still wanted. reject_proposal already notifies the proposer, so
    nothing extra is needed here for that."""
    cycle = CompCycle.objects.select_for_update().get(pk=cycle.pk)
    if cycle.status == CompCycle.Status.CLOSED:
        raise ApprovalError("Cycle is already closed.")

    stragglers = cycle.proposals.select_for_update().filter(status=CompProposal.Status.PROPOSED)
    for proposal in list(stragglers):
        reject_proposal(proposal, approver=actor)

    cycle.status = CompCycle.Status.CLOSED
    cycle.closed_by = actor
    cycle.closed_at = timezone.now()
    cycle.save(update_fields=["status", "closed_by", "closed_at"])
    return cycle
