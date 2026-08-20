"""Service layer for the contract end-date renewal workflow (C1 part 2).
No role/permission checks here -- those belong in the view layer
(EmployeeVersionViewSet.recommend_contract/decide_contract), matching
this codebase's established 403-vs-400 split: wrong role is a view-layer
403, wrong state is a service-layer ContractDecisionError -> 400."""
from __future__ import annotations

from django.utils import timezone

from .models import ContractRenewalDecision, EmployeeVersion, EmploymentEvent


class ContractDecisionError(ValueError):
    """Raised for state-machine violations (re-recommending, re-deciding)."""


def recommend_contract_action(employee_version, *, actor, action, comment="", end_date=None):
    if hasattr(employee_version, "contract_renewal_decision"):
        raise ContractDecisionError("A decision already exists for this contract.")
    if action == ContractRenewalDecision.Action.RENEW and end_date is None:
        raise ContractDecisionError("end_date is required when recommending a renewal.")
    return ContractRenewalDecision.objects.create(
        employee_version=employee_version,
        status=ContractRenewalDecision.Status.RECOMMENDED,
        recommended_action=action,
        recommended_by=actor,
        recommended_at=timezone.now(),
        recommended_comment=comment,
        recommended_end_date=end_date if action == ContractRenewalDecision.Action.RENEW else None,
    )


def decide_contract_action(employee_version, *, actor, action, comment="", end_date=None):
    if action == ContractRenewalDecision.Action.RENEW and end_date is None:
        raise ContractDecisionError("end_date is required when deciding to renew.")

    decision, _ = ContractRenewalDecision.objects.get_or_create(
        employee_version=employee_version,
        defaults={"status": ContractRenewalDecision.Status.RECOMMENDED},
    )
    if decision.status == ContractRenewalDecision.Status.DECIDED:
        raise ContractDecisionError("This contract's decision has already been made.")

    decision.status = ContractRenewalDecision.Status.DECIDED
    decision.decided_action = action
    decision.decided_by = actor
    decision.decided_at = timezone.now()
    decision.decided_comment = comment
    decision.decided_end_date = end_date if action == ContractRenewalDecision.Action.RENEW else None

    employee = employee_version.employee
    effective_date = decision.decided_at.date()

    if action == ContractRenewalDecision.Action.RENEW:
        event = employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.CONTRACT_RENEWAL, effective_date=effective_date,
            contract_end_date=end_date,
        )
        decision.resulting_employee_version = event.to_version
    elif action == ContractRenewalDecision.Action.CONVERT_PERMANENT:
        event = employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.CONTRACT_CONVERSION, effective_date=effective_date,
            employment_status=EmployeeVersion.EmploymentStatus.PERMANENT, contract_end_date=None,
        )
        decision.resulting_employee_version = event.to_version
    elif action == ContractRenewalDecision.Action.LET_LAPSE:
        employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.TERMINATION, effective_date=effective_date,
            termination_reason=EmploymentEvent.TerminationReason.CONTRACT_END,
        )
    else:
        raise ContractDecisionError(f"'{action}' is not a valid decision action.")

    decision.save()
    return decision
