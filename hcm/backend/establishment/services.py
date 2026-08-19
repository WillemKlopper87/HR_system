"""Position approval-chain workflow (C1). hr_admin always proposes and
submits; settings.POSITION_APPROVAL_CHAIN governs everything after that --
see docs/superpowers/specs/2026-08-19-position-establishment-design.md §2.

Role/permission checks are NOT done here (see the plan's Global
Constraints) -- these functions only enforce state-machine validity. The
view layer checks who is allowed to call which action and raises
PermissionDenied (403) before ever reaching these functions; a state-
machine violation from here raises ApprovalError, which the view turns
into a 400.
"""
from __future__ import annotations

from core_hr.models import Employee
from django.conf import settings
from django.db import transaction

from .models import Position, PositionApprovalStep


class ApprovalError(ValueError):
    pass


def _next_post_number() -> str:
    last = Position.objects.order_by("-id").values_list("post_number", flat=True).first()
    if last:
        digits = "".join(ch for ch in last if ch.isdigit())
        n = int(digits) + 1 if digits else 1
    else:
        n = 1
    return f"P-{n:05d}"


def propose_position(
    *, title: str, department, occupational_level, job_grade, location, actor=None
) -> Position:
    return Position.objects.create(
        post_number=_next_post_number(), title=title, department=department,
        occupational_level=occupational_level, job_grade=job_grade, location=location,
        proposed_by=actor,
    )


def submit_for_approval(position: Position, *, actor=None) -> Position:
    if position.status != Position.Status.DRAFT:
        raise ApprovalError(f"Only a draft position can be submitted for approval (currently {position.status}).")
    position.status = Position.Status.IN_REVIEW
    position.current_step = 0
    position.save(update_fields=["status", "current_step"])
    return position


@transaction.atomic
def decide_step(position: Position, *, actor=None, decision: str, comment: str = "") -> Position:
    if position.status != Position.Status.IN_REVIEW:
        raise ApprovalError(f"Position {position.post_number} is not currently in review.")
    chain = settings.POSITION_APPROVAL_CHAIN
    if position.current_step >= len(chain):
        raise ApprovalError(f"Position {position.post_number} has no more approval steps configured.")
    if decision not in (PositionApprovalStep.Decision.APPROVED, PositionApprovalStep.Decision.REJECTED):
        raise ApprovalError(f"'{decision}' is not a valid decision (must be 'approved' or 'rejected').")

    role = chain[position.current_step]
    PositionApprovalStep.objects.create(
        position=position, step_index=position.current_step, role=role, actor=actor,
        decision=decision, comment=comment,
    )

    if decision == PositionApprovalStep.Decision.REJECTED:
        position.status = Position.Status.REJECTED
        position.save(update_fields=["status"])
        return position

    next_step = position.current_step + 1
    if next_step >= len(chain):
        position.status = Position.Status.APPROVED
        position.save(update_fields=["status"])
    else:
        position.current_step = next_step
        position.save(update_fields=["current_step"])
    return position


def revise_and_resubmit(position: Position, *, actor=None, **changed_fields) -> Position:
    """hr_admin only (enforced in the view) -- from `rejected`, may update
    title/department/occupational_level/job_grade/location, then restarts
    the chain from step 0. post_number and prior PositionApprovalStep rows
    are kept: this is a new cycle on the same post identity."""
    if position.status != Position.Status.REJECTED:
        raise ApprovalError(f"Only a rejected position can be revised (currently {position.status}).")
    allowed_fields = {"title", "department", "occupational_level", "job_grade", "location"}
    unknown = set(changed_fields) - allowed_fields
    if unknown:
        raise ApprovalError(f"Cannot change these fields via revise_and_resubmit: {', '.join(sorted(unknown))}.")
    for field, value in changed_fields.items():
        setattr(position, field, value)
    position.status = Position.Status.DRAFT
    position.current_step = 0
    position.save(update_fields=[*changed_fields.keys(), "status", "current_step"])
    return position


def backfill_positions_for_current_employees() -> int:
    """One-time backfill (called from migration 0002): creates exactly one
    approved Position per currently-employed EmployeeVersion that doesn't
    already have one -- 1:1, never grouped/shared even where department+
    grade+title match exactly, since a Position is one seat. No
    PositionApprovalStep rows are fabricated -- this is already-real
    employment, not a new proposal going through review. Idempotent:
    already-linked EmployeeVersions are skipped, safe to call more than
    once (e.g. if the migration is re-run in a dev environment)."""
    created = 0
    for employee in Employee.objects.all():
        version = employee.current_version
        if version is None or version.position_id is not None:
            continue
        position = Position.objects.create(
            post_number=_next_post_number(),
            title=version.job_title,
            department=version.department,
            occupational_level=version.occupational_level,
            job_grade=version.job_grade,
            location=version.location,
            status=Position.Status.APPROVED,
        )
        version.position = position
        version.save(update_fields=["position"])
        created += 1
    return created
