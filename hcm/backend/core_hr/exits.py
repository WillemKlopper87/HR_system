"""Service layer for the employment exit state machine and access cascade
(C1 part 3 — docs/superpowers/specs/2026-08-20-employment-exit-states-design.md).

No role/permission checks here -- those belong in the view layer (a later
slice), matching core_hr/contracts.py's established 403-vs-400 split: wrong
role is a view-layer 403, wrong state is a service-layer
EmploymentChangeError -> 400. The one rule enforced here that reads like a
permission check but isn't: tiered change types require confirmed_by !=
proposed_by (spec §4.2's "second person"). That's the state machine's own
same/different-person rule, decided from identity alone -- it never
consults rbac_audit.permissions for a role, so it stays on this side of
the split. Whether the actor actually HOLDS hr_admin (spec §8's access
table) is, like everywhere else in this module's style, a view-layer 403.

Execution (`execute_employment_change`) is the access cascade itself
(spec §6): revoke roles, disable login, suspend biometric enrolment via
the core_hr/access_cascade.py registry, and -- for ending change types
only -- close employment through the existing `apply_lifecycle_event`.
Nothing here deletes a row; it withdraws access and leaves history
intact (spec §6.3)."""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from rbac_audit.audit import log_access
from rbac_audit.models import AuditLogEntry, RoleAssignment
from rbac_audit.tiers import FieldTier

from . import access_cascade, lifecycle_hooks
from .models import AccessRevocationObligation, EmploymentChange, EmploymentEvent

logger = logging.getLogger(__name__)


class EmploymentChangeError(ValueError):
    """Raised for state-machine violations: propose/confirm/cancel/execute
    out of turn, self-confirmation on a tiered type, a missing reason, or
    a lift with no active suspension to restore."""


def _assert_no_open_change(employee) -> None:
    if EmploymentChange.objects.filter(
        employee=employee, state__in=EmploymentChange.NON_TERMINAL_STATES
    ).exists():
        raise EmploymentChangeError(
            f"Employee {employee.employee_number} already has an employment change in progress."
        )


def _active_suspension_for(employee):
    """The employee's most recent executed SUSPENSION that hasn't already
    been lifted -- "the matching suspension" spec §6.2 restores against.
    An employee can be suspended and lifted more than once over their
    career, so this can't just be "the newest suspension row"; it has to
    exclude any suspension a LIFT_SUSPENSION has already executed against."""
    already_lifted_ids = EmploymentChange.objects.filter(
        employee=employee, change_type=EmploymentChange.ChangeType.LIFT_SUSPENSION,
        state=EmploymentChange.State.EXECUTED, lifts_suspension__isnull=False,
    ).values_list("lifts_suspension_id", flat=True)
    return (
        EmploymentChange.objects.filter(
            employee=employee, change_type=EmploymentChange.ChangeType.SUSPENSION,
            state=EmploymentChange.State.EXECUTED,
        )
        .exclude(id__in=list(already_lifted_ids))
        .order_by("-executed_at")
        .first()
    )


@transaction.atomic
def propose_employment_change(employee, *, actor, change_type, effective_date, reason):
    if change_type not in EmploymentChange.ChangeType.values:
        raise EmploymentChangeError(f"'{change_type}' is not a valid change type.")
    if not reason or not reason.strip():
        raise EmploymentChangeError("A reason is required.")
    _assert_no_open_change(employee)

    lifts_suspension = None
    if change_type == EmploymentChange.ChangeType.LIFT_SUSPENSION:
        lifts_suspension = _active_suspension_for(employee)
        if lifts_suspension is None:
            raise EmploymentChangeError(
                f"Employee {employee.employee_number} has no active suspension to lift."
            )
    if change_type == EmploymentChange.ChangeType.DISMISSAL_SUMMARY:
        # Spec §4.2: "Effective date is today by definition" -- a summary
        # dismissal is immediate by construction, not by caller choice.
        effective_date = timezone.localdate()

    return EmploymentChange.objects.create(
        employee=employee, change_type=change_type, state=EmploymentChange.State.PROPOSED,
        effective_date=effective_date, reason=reason, proposed_by=actor, proposed_at=timezone.now(),
        lifts_suspension=lifts_suspension,
    )


@transaction.atomic
def confirm_employment_change(change: EmploymentChange, *, actor):
    if change.state != EmploymentChange.State.PROPOSED:
        raise EmploymentChangeError(f"Cannot confirm a change in '{change.state}' state.")
    if change.change_type in EmploymentChange.TIERED_CHANGE_TYPES and actor.id == change.proposed_by_id:
        raise EmploymentChangeError(
            "This change requires a different person to confirm it (spec §4.2 — CCMA-exposed or hard to undo)."
        )
    change.state = EmploymentChange.State.CONFIRMED
    change.confirmed_by = actor
    change.confirmed_at = timezone.now()
    change.save(update_fields=["state", "confirmed_by", "confirmed_at"])

    # Spec §2.3: execution fires on the effective date, immediately when
    # that date is today or already past.
    if change.effective_date <= timezone.localdate():
        execute_employment_change(change)
    return change


@transaction.atomic
def cancel_employment_change(change: EmploymentChange, *, actor, reason: str = ""):
    if change.state not in EmploymentChange.NON_TERMINAL_STATES:
        raise EmploymentChangeError(f"Cannot cancel a change in '{change.state}' state.")
    change.state = EmploymentChange.State.CANCELLED
    change.cancelled_by = actor
    change.cancelled_at = timezone.now()
    change.cancellation_reason = reason
    change.save(update_fields=["state", "cancelled_by", "cancelled_at", "cancellation_reason"])
    return change


def _log(*, actor, entity_type, employee_id, detail) -> None:
    log_access(
        actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type=entity_type,
        entity_id=employee_id, field_tier=FieldTier.INTERNAL, fields_touched=detail,
    )


def _withdraw_access(change: EmploymentChange, employee, actor) -> None:
    """Cascade steps 1-3 (spec §6.1) -- shared by every ending type AND by
    SUSPENSION, since a suspended person needs exactly the same access
    withdrawal as someone leaving for good; step 4 (closing employment) is
    the caller's job, only for ending types."""
    revoked = list(RoleAssignment.objects.filter(employee=employee, revoked_at__isnull=True))
    if revoked:
        RoleAssignment.objects.filter(id__in=[r.id for r in revoked]).update(revoked_at=timezone.now())
        change.revoked_role_assignments.set(revoked)
        _log(
            actor=actor, entity_type="rbac_audit.RoleAssignment", employee_id=employee.id,
            detail=(
                f"revoked {len(revoked)} role assignment(s) for employment_change #{change.pk} "
                f"({change.change_type}): {', '.join(r.role.name for r in revoked)}"
            ),
        )

    if employee.user_id is not None and employee.user.is_active:
        employee.user.is_active = False
        employee.user.save(update_fields=["is_active"])
        change.login_disabled_by_change = True
        _log(
            actor=actor, entity_type="auth.User", employee_id=employee.id,
            detail=f"login disabled for employment_change #{change.pk} ({change.change_type})",
        )

    handler_results = access_cascade.run_exit_handlers(employee)
    change.exit_handler_effects = handler_results
    failed_domains = set(access_cascade.registered_exit_handlers()) - set(handler_results.keys())
    now = timezone.now()
    for name in access_cascade.registered_exit_handlers():
        failed = name in failed_domains
        AccessRevocationObligation.objects.create(
            employment_change=change, domain=name,
            status=AccessRevocationObligation.Status.FAILED if failed else AccessRevocationObligation.Status.SUCCESS,
            completed_at=None if failed else now,
            error_detail="handler raised an exception; see server logs for the traceback" if failed else "",
        )
    if failed_domains:
        change.access_complete = False
        _log(
            actor=actor, entity_type="core_hr.AccessRevocationObligation", employee_id=employee.id,
            detail=(
                f"access NOT complete for employment_change #{change.pk} ({change.change_type}): "
                f"failed domain(s): {', '.join(sorted(failed_domains))}"
            ),
        )
    for name, count in handler_results.items():
        if count:
            _log(
                actor=actor, entity_type=name, employee_id=employee.id,
                detail=f"{count} row(s) suspended for employment_change #{change.pk} ({change.change_type})",
            )


def _restore_access(change: EmploymentChange, employee, actor) -> None:
    """Spec §6.2: restore precisely what the matching suspension revoked.
    A restored grant is a NEW RoleAssignment referencing the lift, not an
    un-revocation of the old row -- the system records that access was
    removed and later returned, rather than pretending the revocation
    never happened."""
    suspension = change.lifts_suspension
    already_active_role_ids = set(
        RoleAssignment.objects.filter(employee=employee, revoked_at__isnull=True).values_list("role_id", flat=True)
    )
    to_restore = [
        assignment for assignment in suspension.revoked_role_assignments.select_related("role").all()
        if assignment.role_id not in already_active_role_ids
    ]
    if to_restore:
        RoleAssignment.objects.bulk_create([
            RoleAssignment(employee=employee, role=assignment.role, granted_by=actor)
            for assignment in to_restore
        ])
        _log(
            actor=actor, entity_type="rbac_audit.RoleAssignment", employee_id=employee.id,
            detail=(
                f"restored {len(to_restore)} role assignment(s) for employment_change #{change.pk}: "
                f"{', '.join(a.role.name for a in to_restore)}"
            ),
        )

    if suspension.login_disabled_by_change and employee.user_id is not None and not employee.user.is_active:
        employee.user.is_active = True
        employee.user.save(update_fields=["is_active"])
        _log(
            actor=actor, entity_type="auth.User", employee_id=employee.id,
            detail=f"login re-enabled for employment_change #{change.pk} ({change.change_type})",
        )

    affected_domains = {name for name, count in suspension.exit_handler_effects.items() if count}
    for name, count in access_cascade.run_restore_handlers(employee, only=affected_domains).items():
        if count:
            _log(
                actor=actor, entity_type=name, employee_id=employee.id,
                detail=f"{count} row(s) restored for employment_change #{change.pk} ({change.change_type})",
            )


@transaction.atomic
def execute_employment_change(change: EmploymentChange) -> EmploymentChange:
    if change.state != EmploymentChange.State.CONFIRMED:
        raise EmploymentChangeError(f"Cannot execute a change in '{change.state}' state.")
    employee = change.employee
    actor = change.confirmed_by

    if change.change_type == EmploymentChange.ChangeType.LIFT_SUSPENSION:
        _restore_access(change, employee, actor)
    else:
        _withdraw_access(change, employee, actor)
        if change.change_type in EmploymentChange.ENDING_CHANGE_TYPES:
            termination_reason = EmploymentChange.TERMINATION_REASON_BY_CHANGE_TYPE[change.change_type]
            # apply_lifecycle_event raises a bare ValueError (not
            # EmploymentChangeError) if effective_date isn't after the
            # current version's valid_from -- e.g. someone hired and
            # summary-dismissed the same day. contracts.py's
            # decide_contract_action translates the equivalent case
            # because it proved that branch reachable and specific; here
            # it's left untranslated (a real ValueError still surfaces,
            # just under apply_lifecycle_event's own message) -- a known,
            # narrow gap rather than a silently swallowed one.
            event = employee.apply_lifecycle_event(
                event_type=EmploymentEvent.EventType.TERMINATION,
                effective_date=change.effective_date,
                termination_reason=termination_reason,
                notes=change.reason,
            )
            change.resulting_event = event
            _log(
                actor=actor, entity_type="core_hr.EmploymentEvent", employee_id=employee.id,
                detail=(
                    f"employment closed for employment_change #{change.pk} ({change.change_type}); "
                    f"termination_reason={termination_reason}"
                ),
            )
            # C1 part 3 slice 3 (onboarding/offboarding checklists design
            # spec §6.2): fires only here, for ENDING types, never for
            # SUSPENSION -- a suspended employee hasn't left. Additive only;
            # does not touch the access-cascade steps above.
            lifecycle_hooks.run_exit_completion_handlers(employee, change)
        # SUSPENSION: no lifecycle event, no version change (spec §2.1) --
        # the employee stays open on their current version.

    change.state = EmploymentChange.State.EXECUTED
    change.executed_at = timezone.now()
    change.save(update_fields=[
        "state", "executed_at", "resulting_event",
        "login_disabled_by_change", "exit_handler_effects", "access_complete",
    ])
    return change


@transaction.atomic
def retry_access_revocation(change: EmploymentChange, *, actor) -> dict[str, int]:
    """H-2: re-run only the cascade domains a prior withdrawal recorded as
    FAILED (`AccessRevocationObligation.Status.FAILED`), so a transient
    handler outage doesn't leave `access_complete` wrong forever. Updates
    each retried obligation in place rather than creating new rows, and is
    a no-op -- returns `{}`, changes nothing -- when there is nothing left
    to retry, so calling it again after everything already succeeded is
    safe."""
    if change.change_type == EmploymentChange.ChangeType.LIFT_SUSPENSION:
        raise EmploymentChangeError("Only a withdrawal's own obligations can be retried.")
    if change.state != EmploymentChange.State.EXECUTED:
        raise EmploymentChangeError(f"Cannot retry access revocation for a change in '{change.state}' state.")

    failing = list(change.revocation_obligations.filter(status=AccessRevocationObligation.Status.FAILED))
    if not failing:
        return {}

    employee = change.employee
    retry_names = {obligation.domain for obligation in failing}
    handler_results = access_cascade.run_exit_handlers(employee, only=retry_names)
    now = timezone.now()
    for obligation in failing:
        obligation.attempt_count += 1
        if obligation.domain in handler_results:
            obligation.status = AccessRevocationObligation.Status.SUCCESS
            obligation.completed_at = now
            obligation.error_detail = ""
        obligation.save(update_fields=["attempt_count", "status", "completed_at", "error_detail", "last_attempt_at"])

    change.exit_handler_effects = {**change.exit_handler_effects, **handler_results}
    change.access_complete = not change.revocation_obligations.filter(
        status=AccessRevocationObligation.Status.FAILED
    ).exists()
    change.save(update_fields=["exit_handler_effects", "access_complete"])

    for name, count in handler_results.items():
        if count:
            _log(
                actor=actor, entity_type=name, employee_id=employee.id,
                detail=f"{count} row(s) suspended on retry for employment_change #{change.pk} ({change.change_type})",
            )
    if change.access_complete:
        _log(
            actor=actor, entity_type="core_hr.AccessRevocationObligation", employee_id=employee.id,
            detail=f"access now complete for employment_change #{change.pk} after retry",
        )
    return handler_results


@transaction.atomic
def record_executed_exit(employee, *, actor, change_type, effective_date, reason) -> EmploymentChange:
    """Record an exit that is *already decided elsewhere* and execute it
    immediately, skipping propose->confirm.

    This is not a back door around spec §5's review gate; it is for callers
    that carry their own, equivalent governance and would otherwise impose a
    second approval on one decision. The only such caller today is
    `contracts.py`'s `let_lapse`: a fixed-term contract expiring has already
    been through C1 part 2's recommend->decide handshake, which is a
    two-actor review of exactly this question. Making HR then confirm an
    `EmploymentChange` as well would be asking the same question twice.

    What it deliberately does NOT skip is the cascade: it runs the identical
    `execute_employment_change` path every other exit runs, so access
    withdrawal, audit logging and the `EmploymentEvent` are byte-for-byte the
    same however the exit arrived. That is the point -- before this existed,
    `let_lapse` closed employment while leaving roles, login and biometric
    enrolment fully live.

    Anything genuinely originating in HR (dismissals, suspensions,
    resignations) must still go through `propose_employment_change`."""
    if change_type not in EmploymentChange.ENDING_CHANGE_TYPES:
        raise EmploymentChangeError(
            f"'{change_type}' is not an ending change type; only exits that are already "
            "decided elsewhere may skip the review gate."
        )
    # An open proposal means someone is mid-decision about this person (a
    # suspension pending a hearing, say). Surfacing that as a domain error
    # beats letting the one_open_employment_change_per_employee constraint
    # fire as an IntegrityError -- and it is a genuine conflict a human
    # should resolve rather than something to resolve automatically.
    _assert_no_open_change(employee)
    change = EmploymentChange.objects.create(
        employee=employee, change_type=change_type,
        state=EmploymentChange.State.CONFIRMED,
        effective_date=effective_date, reason=reason,
        proposed_by=actor, proposed_at=timezone.now(),
        confirmed_by=actor, confirmed_at=timezone.now(),
    )
    return execute_employment_change(change)


def execute_due_employment_changes() -> dict:
    """The scheduled half of spec §2.3: every CONFIRMED change whose
    effective_date has arrived (today or already past). Called from the
    existing daily beat job (core_hr/tasks.py) -- a change with a future
    effective_date is left alone until its own day. Failures are isolated
    per change, the same isolation policy as data_quality.py/retention.py:
    one broken execution must not block every other employee's exit."""
    today = timezone.localdate()
    due = EmploymentChange.objects.filter(
        state=EmploymentChange.State.CONFIRMED, effective_date__lte=today
    )
    executed = 0
    errors = 0
    for change in due:
        try:
            with transaction.atomic():
                execute_employment_change(change)
            executed += 1
        except Exception:  # noqa: BLE001 -- isolate per change, keep sweeping
            errors += 1
            logger.exception("exits: failed to execute EmploymentChange #%s", change.pk)
    return {"executed": executed, "errors": errors}
