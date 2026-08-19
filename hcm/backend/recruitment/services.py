from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from core_hr.models import Employee, EmployeeVersion
from establishment.models import Position

from .models import Applicant, ApplicantStageEvent, Requisition


class StageTransitionError(ValueError):
    pass


def validate_requisition_positions(positions, *, headcount: int, requisition=None) -> None:
    """Raises ValueError (caught by the serializer, surfaced as a 400) if
    the linked positions don't satisfy C1's establishment-control rules.
    Already-linked positions (requisition.positions before this call) are
    exempt from the approved/vacant/unclaimed checks -- a position this
    SAME requisition already committed to stays valid even once one of its
    own hires has since filled it; only newly-added positions are held to
    the strict bar."""
    if len(positions) != headcount:
        raise ValueError(
            f"{len(positions)} position(s) linked but headcount is {headcount} -- they must match."
        )

    already_linked_ids = set(requisition.positions.values_list("id", flat=True)) if requisition else set()

    for position in positions:
        if position.id in already_linked_ids:
            continue
        if position.status != Position.Status.APPROVED:
            raise ValueError(f"Position {position.post_number} is not approved yet.")
        if not position.is_vacant:
            raise ValueError(f"Position {position.post_number} is not vacant.")
        claimed_by = position.requisitions.exclude(
            status__in=[Requisition.Status.CLOSED, Requisition.Status.FILLED]
        )
        if requisition is not None:
            claimed_by = claimed_by.exclude(pk=requisition.pk)
        if claimed_by.exists():
            raise ValueError(f"Position {position.post_number} is already linked to another open requisition.")


def _next_employee_number() -> str:
    last = Employee.objects.order_by("-employee_number").values_list("employee_number", flat=True).first()
    if last:
        digits = "".join(ch for ch in last if ch.isdigit())
        n = int(digits) + 1 if digits else 1
    else:
        n = 1
    return f"E{n:05d}"


@transaction.atomic
def transition_applicant(
    applicant: Applicant, *, to_stage: str, actor=None, notes: str = "", rejected_reason: str = "", hire_date=None
) -> Applicant:
    """Moves an applicant to a new pipeline stage, recording the
    transition (ApplicantStageEvent — feeds the recruitment dashboard's
    time-to-fill metric). Moving to HIRED additionally runs the
    hire-to-employee flow (Sprint 4 acceptance criterion: no re-entry)."""
    if not applicant.can_transition_to(to_stage):
        raise StageTransitionError(f"Cannot move from '{applicant.current_stage}' to '{to_stage}'.")

    from_stage = applicant.current_stage
    applicant.current_stage = to_stage
    update_fields = ["current_stage"]
    if to_stage == Applicant.Stage.REJECTED and rejected_reason:
        applicant.rejected_reason = rejected_reason
        update_fields.append("rejected_reason")
    applicant.save(update_fields=update_fields)

    ApplicantStageEvent.objects.create(
        applicant=applicant, from_stage=from_stage, to_stage=to_stage, changed_by=actor, notes=notes
    )

    if to_stage == Applicant.Stage.HIRED:
        _complete_hire(applicant, hire_date=hire_date or timezone.localdate())

    return applicant


def _complete_hire(applicant: Applicant, *, hire_date) -> Employee:
    requisition = applicant.requisition

    # Checked up front so a duplicate work_email surfaces as a clear error
    # rather than exhausting the employee_number retry loop below and
    # reporting the wrong cause — retrying a new employee_number can never
    # fix a work_email collision.
    if Employee.objects.filter(work_email=applicant.email).exists():
        raise ValueError(f"An employee with work email '{applicant.email}' already exists — cannot complete hire.")

    employee = None
    for _attempt in range(5):
        employee_number = _next_employee_number()
        try:
            with transaction.atomic():
                employee = Employee.objects.hire(
                    employee_number=employee_number,
                    first_name=applicant.first_name,
                    last_name=applicant.last_name,
                    date_of_birth=applicant.date_of_birth,
                    work_email=applicant.email,
                    hire_date=hire_date,
                    department=requisition.department,
                    occupational_level=requisition.occupational_level,
                    job_grade=requisition.job_grade,
                    location=requisition.location,
                    manager=requisition.hiring_manager,
                    race=applicant.race,
                    gender=applicant.gender,
                    disability_status=applicant.disability_status,
                    race_source=EmployeeVersion.DemographicSource.SELF_IDENTIFIED,
                    disability_source=EmployeeVersion.DemographicSource.SELF_IDENTIFIED,
                )
        except IntegrityError:
            continue
        else:
            break
    if employee is None:
        raise RuntimeError("Could not allocate a unique employee number after 5 attempts")

    applicant.resulting_employee = employee
    applicant.save(update_fields=["resulting_employee"])

    if requisition.hired_count >= requisition.headcount and requisition.status != Requisition.Status.FILLED:
        requisition.status = Requisition.Status.FILLED
        requisition.closed_at = timezone.localdate()
        requisition.save(update_fields=["status", "closed_at"])

    return employee
