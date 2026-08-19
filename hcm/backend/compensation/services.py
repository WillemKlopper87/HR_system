from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from notifications.services import notify

from .models import CompProposal, PayBand


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


@transaction.atomic
def propose_compensation_change(
    *, employee, proposed_annual_salary, justification: str = "", proposed_by=None, effective_date=None
) -> CompProposal:
    version = employee.current_version
    if version is None or version.job_grade_id is None:
        raise ValueError("Employee has no current job grade to evaluate a compensation proposal against.")
    return CompProposal.objects.create(
        employee=employee,
        current_job_grade=version.job_grade,
        proposed_annual_salary=proposed_annual_salary,
        justification=justification,
        status=CompProposal.Status.PROPOSED,
        requires_override=evaluate_requires_override(employee, proposed_annual_salary),
        proposed_by=proposed_by,
        effective_date=effective_date,
    )


def approve_proposal(proposal: CompProposal, *, approver, override_reason: str = "") -> CompProposal:
    if proposal.status != CompProposal.Status.PROPOSED:
        raise ApprovalError("Only a proposed compensation change can be approved.")
    if approver is not None and proposal.proposed_by_id == approver.id:
        raise ApprovalError("The proposer cannot also approve this compensation change (segregation of duties).")
    if proposal.requires_override and not override_reason:
        raise ApprovalError(
            "This proposal is outside the pay band — an override reason is required to approve it."
        )

    proposal.status = CompProposal.Status.APPROVED
    proposal.approved_by = approver
    proposal.approved_at = timezone.now()
    update_fields = ["status", "approved_by", "approved_at"]
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
