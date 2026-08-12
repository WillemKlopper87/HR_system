from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from core_hr.models import Employee, EmployeeVersion

from .models import Applicant, ApplicantStageEvent, Requisition


class StageTransitionError(ValueError):
    pass


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
