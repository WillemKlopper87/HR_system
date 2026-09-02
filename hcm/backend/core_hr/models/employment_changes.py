"""The propose -> confirm -> execute exit/suspension workflow. Split out of
models.py (HR_Code_report.md M5) -- no behavior change; see
core_hr/models/__init__.py for the app's overall split. Imported before
exit_interviews.py in __init__.py since ExitInterview holds a direct FK
to EmploymentChange... actually that FK is a lazy string reference
("EmploymentChange"), so ordering between the two doesn't matter -- kept
here anyway to mirror the views_employment_changes.py /
views_exit_interviews.py split order."""
from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from ..base import TimestampedModel
from .core import Employee, EmploymentEvent


class EmploymentChange(TimestampedModel):
    """The propose -> confirm -> execute object for an employment exit or a
    suspension (C1 part 3, design spec
    docs/superpowers/specs/2026-08-20-employment-exit-states-design.md).
    One row per proposed change; the state machine and the access cascade
    it triggers on execution live in `core_hr/exits.py` (deliberately not
    here, mirroring how ContractRenewalDecision's workflow lives in
    `contracts.py` rather than on the model).

    `change_type` is either an ENDING type (closes employment via
    `apply_lifecycle_event` on execution) or SUSPENSION/LIFT_SUSPENSION,
    which never do (spec §2.1 — suspension is an access overlay on
    continuing employment, not a lifecycle event; modelling it as one would
    corrupt the EEA2 termination count). TIERED_CHANGE_TYPES are the ones
    spec §3/§4.2 requires a *different* second person to confirm
    (CCMA-exposed or hardest to undo); the rest, the proposer may confirm
    themselves."""

    class ChangeType(models.TextChoices):
        SUSPENSION = "suspension", "Suspension"
        LIFT_SUSPENSION = "lift_suspension", "Lift suspension"
        DISMISSAL_SUMMARY = "dismissal_summary", "Summary dismissal"
        DISMISSAL_MISCONDUCT = "dismissal_misconduct", "Dismissal — misconduct"
        DISMISSAL_INCAPACITY = "dismissal_incapacity", "Dismissal — incapacity"
        OPERATIONAL_REQUIREMENTS = "operational_requirements", "Operational requirements"
        RESIGNATION = "resignation", "Resignation"
        RETIREMENT = "retirement", "Retirement"
        CONTRACT_END = "contract_end", "Contract end"
        DEATH = "death", "Death"

    class State(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        CONFIRMED = "confirmed", "Confirmed"
        EXECUTED = "executed", "Executed"
        CANCELLED = "cancelled", "Cancelled"

    # Spec §4.2's confirmation-tier column: these six require confirmed_by
    # != proposed_by. The remaining four (RESIGNATION, RETIREMENT,
    # CONTRACT_END, DEATH) are "proposer confirms" -- routine leavers
    # aren't bottlenecked on a second signature.
    TIERED_CHANGE_TYPES = frozenset({
        ChangeType.SUSPENSION, ChangeType.LIFT_SUSPENSION, ChangeType.DISMISSAL_SUMMARY,
        ChangeType.DISMISSAL_MISCONDUCT, ChangeType.DISMISSAL_INCAPACITY,
        ChangeType.OPERATIONAL_REQUIREMENTS,
    })
    # Everything except SUSPENSION/LIFT_SUSPENSION ends employment (spec §4.2
    # table's "Ends employment" column).
    ENDING_CHANGE_TYPES = frozenset({
        ChangeType.DISMISSAL_SUMMARY, ChangeType.DISMISSAL_MISCONDUCT, ChangeType.DISMISSAL_INCAPACITY,
        ChangeType.OPERATIONAL_REQUIREMENTS, ChangeType.RESIGNATION, ChangeType.RETIREMENT,
        ChangeType.CONTRACT_END, ChangeType.DEATH,
    })
    NON_TERMINAL_STATES = frozenset({State.PROPOSED, State.CONFIRMED})

    # Spec §4.2: "The ending types map onto the existing
    # EmploymentEvent.TerminationReason values ... no new termination
    # vocabulary is introduced." TerminationReason has exactly one value per
    # *ground* (misconduct/incapacity/operational requirements/resignation/
    # retirement/death/contract end) -- seven, for eight ending change
    # types. DISMISSAL_SUMMARY is not a distinct ground; a summary
    # dismissal (immediate, no notice) is the standard outcome of a
    # misconduct finding for serious/gross misconduct under the LRA, so it
    # maps onto the same DISMISSAL_MISCONDUCT reason as the non-summary
    # path -- the two change types differ in process/immediacy, not in the
    # statutory ground reported to EEA2.
    TERMINATION_REASON_BY_CHANGE_TYPE = {
        ChangeType.DISMISSAL_SUMMARY: EmploymentEvent.TerminationReason.DISMISSAL_MISCONDUCT,
        ChangeType.DISMISSAL_MISCONDUCT: EmploymentEvent.TerminationReason.DISMISSAL_MISCONDUCT,
        ChangeType.DISMISSAL_INCAPACITY: EmploymentEvent.TerminationReason.DISMISSAL_INCAPACITY,
        ChangeType.OPERATIONAL_REQUIREMENTS: EmploymentEvent.TerminationReason.OPERATIONAL_REQUIREMENTS,
        ChangeType.RESIGNATION: EmploymentEvent.TerminationReason.RESIGNATION,
        ChangeType.RETIREMENT: EmploymentEvent.TerminationReason.RETIREMENT,
        ChangeType.CONTRACT_END: EmploymentEvent.TerminationReason.CONTRACT_END,
        ChangeType.DEATH: EmploymentEvent.TerminationReason.DEATH,
    }

    employee = models.ForeignKey(Employee, related_name="employment_changes", on_delete=models.CASCADE)
    change_type = models.CharField(max_length=30, choices=ChangeType.choices)
    state = models.CharField(max_length=20, choices=State.choices, default=State.PROPOSED)
    effective_date = models.DateField()
    # Free text, required (enforced in the service layer, not here -- see
    # exits.py's module docstring on why domain rules live there rather
    # than as a bare model constraint). "A dismissal without a recorded
    # reason is not defensible" (spec §4.1).
    reason = models.TextField()

    proposed_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="+")
    proposed_at = models.DateTimeField()
    confirmed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    # Set only for change_type=LIFT_SUSPENSION -- the SUSPENSION row this
    # lift restores access for (spec §6.2). Self-FK, so no new peer-app
    # coupling. PROTECT: this link is the only way execute() knows which
    # revoked_role_assignments to restore: it must never silently vanish.
    lifts_suspension = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="lifted_by",
    )
    # The RoleAssignment rows THIS change revoked on execution, so a lift
    # restores precisely those rather than guessing (spec §4.1/§6.2).
    # String FK -- rbac_audit is shared kernel (importable from core_hr),
    # but every other cross-app FK in this file already uses the string
    # form (see `position` above), so this follows the same convention
    # rather than adding the one direct model import in this module.
    revoked_role_assignments = models.ManyToManyField(
        "rbac_audit.RoleAssignment", blank=True, related_name="revoked_by_employment_changes",
    )
    # The EmploymentEvent this execution produced -- null for SUSPENSION/
    # LIFT_SUSPENSION, which create none (spec §2.1/§4.1).
    resulting_event = models.ForeignKey(
        EmploymentEvent, null=True, blank=True, on_delete=models.SET_NULL, related_name="employment_change",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-proposed_at"]
        constraints = [
            # Spec §5: "Only one non-terminal EmploymentChange may exist
            # per employee at a time, so two people can't independently
            # propose conflicting exits." DB-enforced, not just checked in
            # the service layer -- the same belt-and-suspenders pattern as
            # RoleAssignment's one_active_assignment_per_employee_role and
            # DataQualityException's one_open_exception_per_employee_type.
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(state__in=["proposed", "confirmed"]),
                name="one_open_employment_change_per_employee",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.get_change_type_display()} ({self.state})"
