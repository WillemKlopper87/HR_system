"""Service layer for the contract end-date renewal workflow (C1 part 2).
No role/permission checks here -- those belong in the view layer
(EmployeeVersionViewSet.recommend_contract/decide_contract), matching
this codebase's established 403-vs-400 split: wrong role is a view-layer
403, wrong state is a service-layer ContractDecisionError -> 400."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import ContractRenewalDecision, EmployeeVersion, EmploymentEvent


class ContractDecisionError(ValueError):
    """Raised for state-machine violations (re-recommending, re-deciding)."""


def _assert_actionable(employee_version):
    """Both actions are only ever meaningful on the employee's CURRENT,
    FIXED_TERM version. Neither was checked before, and these two service
    functions are the only API-reachable callers of
    `Employee.apply_lifecycle_event` in the whole backend — so this is the
    sole guard standing between the API and a corrupt employment record:

    * **Not fixed-term.** `let_lapse` on a PERMANENT employee terminates
      them with `termination_reason=CONTRACT_END`; `EmploymentEvent` is the
      EEA2 statutory workforce-movement source, so that is corrupt
      statutory data. Symmetrically, `renew` writes a `contract_end_date`
      onto a PERMANENT version — an inconsistent state nothing detects.
      The FIXED_TERM scoping the design spec assumes throughout (§3.1, §5,
      §7, §9) lived nowhere in code.
    * **Not the current version.** `apply_lifecycle_event` always operates
      on `versions.filter(valid_to__isnull=True).first()`, while the
      decision row is written against `employee_version`. Deciding on a
      historical closed version therefore recorded the decision on V1
      while the event closed V2 — one act split across two rows of the
      audit trail.

    `EmployeeVersionViewSet.get_queryset()` deliberately returns the
    UNFILTERED queryset for non-list actions (so `RowScopePermission` can
    log a block rather than 404), which is right for reads but means
    `?fixed_term=true` never constrains these writes; and the frontend
    only ever lists `current=true` rows. Both paths are wide open via the
    API, so the check belongs here.

    Domain state, not role — so `ContractDecisionError` -> 400, matching
    every other rule in this module (see the module docstring)."""
    if employee_version.valid_to is not None:
        raise ContractDecisionError("Only the employee's current version can be actioned.")
    if employee_version.employment_status != EmployeeVersion.EmploymentStatus.FIXED_TERM:
        raise ContractDecisionError("Only fixed-term contracts have a renewal decision.")


def _validate_renewal_end_date(employee_version, end_date, *, required_message):
    """Spec §4: a renewal's new `end_date` "must be after the version's
    current `contract_end_date`". A renewal *extends* a contract; it must
    never mint one that already expired.

    Why this is a hard 400 rather than a soft warning: nothing downstream
    ever surfaces an already-expired fixed-term version again.
    contract_reminders.py matches `contract_end_date - today` against
    CONTRACT_REMINDER_OFFSETS_DAYS, so a negative days_remaining can never
    hit an offset; the MISSING_CONTRACT_END_DATE data-quality check only
    fires on NULL, not on "set, but in the past"; and spec §11 deliberately
    defers a past-end-date check. A fat-fingered 2017-12-31 would be a
    permanent, silent black hole.

    The binding floor is therefore the *later* of the stored date and
    today, which closes three cases with one comparison:

    * **No stored date.** Spec §7 leaves the pre-existing fixed-term
      population un-backfilled (NULL, flagged by
      MISSING_CONTRACT_END_DATE), so these functions are genuinely
      reachable with nothing to order against. Skipping the check there
      would leave the identical black hole open through the identical code
      path, so today is the bound.
    * **Stored date in the future** -- the ordinary case. The new date must
      extend past the one it replaces.
    * **Stored date already in the past** -- a contract that lapsed with
      nobody deciding, a state spec §11 explicitly acknowledges is live.
      Ordering against the stored date alone would accept a renewal that is
      after the old expiry but still before today, minting precisely the
      already-expired version this function exists to prevent. Today binds
      instead.

    Today is the honest bound in every case: the resulting version is
    created with today's effective date (see `effective_date` below), so an
    end date on or before today describes a contract that is over before it
    starts. Genuine historical corrections go through Django admin
    (spec §7), not through this workflow.
    """
    if end_date is None:
        raise ContractDecisionError(required_message)
    today = timezone.localdate()
    stored = employee_version.contract_end_date
    floor = stored if stored is not None and stored > today else today
    if end_date > floor:
        return
    if stored is None:
        raise ContractDecisionError(
            "The new contract end date must be in the future "
            "(this version has no current contract end date to extend)."
        )
    if stored <= today:
        raise ContractDecisionError(
            f"The current contract end date ({stored:%Y-%m-%d}) has already passed; "
            "the new one must be in the future."
        )
    raise ContractDecisionError(
        f"The new contract end date must be after the current one ({stored:%Y-%m-%d})."
    )


def recommend_contract_action(employee_version, *, actor, action, comment="", end_date=None):
    _assert_actionable(employee_version)
    if action not in ContractRenewalDecision.Action.values:
        raise ContractDecisionError(f"'{action}' is not a valid recommendation action.")
    if hasattr(employee_version, "contract_renewal_decision"):
        raise ContractDecisionError("A decision already exists for this contract.")
    if action == ContractRenewalDecision.Action.RENEW:
        _validate_renewal_end_date(
            employee_version, end_date,
            required_message="end_date is required when recommending a renewal.",
        )
    return ContractRenewalDecision.objects.create(
        employee_version=employee_version,
        status=ContractRenewalDecision.Status.RECOMMENDED,
        recommended_action=action,
        recommended_by=actor,
        recommended_at=timezone.now(),
        recommended_comment=comment,
        recommended_end_date=end_date if action == ContractRenewalDecision.Action.RENEW else None,
    )


@transaction.atomic
def decide_contract_action(employee_version, *, actor, action, comment="", end_date=None):
    _assert_actionable(employee_version)
    if action == ContractRenewalDecision.Action.RENEW:
        _validate_renewal_end_date(
            employee_version, end_date,
            required_message="end_date is required when deciding to renew.",
        )

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

    try:
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
            # Known, deliberate gap (C1 part 3 — design spec
            # docs/superpowers/specs/2026-08-20-employment-exit-states-design.md):
            # this still calls apply_lifecycle_event directly rather than
            # going through core_hr/exits.py's EmploymentChange cascade, so
            # a lapsed contract closes employment correctly but does NOT
            # revoke role assignments, disable the login, or suspend the
            # biometric enrolment the way every other termination path now
            # does. Not routed through EmploymentChange yet because that
            # service requires a non-blank `reason` (this workflow only
            # ever collects an optional `comment`) and can raise a new
            # EmploymentChangeError this call site and its callers don't
            # handle -- see Data-Dictionary.md's employment_change section
            # for the full reasoning and the intended follow-up.
            employee.apply_lifecycle_event(
                event_type=EmploymentEvent.EventType.TERMINATION, effective_date=effective_date,
                termination_reason=EmploymentEvent.TerminationReason.CONTRACT_END,
            )
        else:
            raise ContractDecisionError(f"'{action}' is not a valid decision action.")
    except ContractDecisionError:
        # Pass through unchanged -- the invalid-action branch above raises
        # its own ContractDecisionError (itself a ValueError subclass); it
        # must not fall into the generic ValueError handling below and get
        # double-wrapped with a misleading message.
        raise
    except ValueError as exc:
        # apply_lifecycle_event raises a bare ValueError for two
        # conditions, and this message is specific to one of them, so it
        # is only correct because the other is unreachable from here:
        #
        #  * "has no open version to close" — unreachable. It fires when
        #    `versions.filter(valid_to__isnull=True).first()` is None, but
        #    _assert_actionable above has already established that
        #    `employee_version.valid_to is None`, and employee_version
        #    belongs to this same employee, so that queryset has at least
        #    one row. (Before the current-version guard existed, this
        #    condition WAS reachable — for an already-terminated employee
        #    — and surfaced under the misleading "already changed today"
        #    wording below.)
        #  * "effective_date must be after the current version's
        #    valid_from" — reachable, and exactly what the message
        #    describes: a second same-day decision landing on a version
        #    whose valid_from is also today.
        #
        # Translated into the same 400 path every other state-machine
        # violation in this module uses, instead of surfacing as a 500.
        raise ContractDecisionError(
            "This employee's record already changed today — try again tomorrow."
        ) from exc

    decision.save()
    return decision
