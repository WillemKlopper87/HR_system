from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from core_hr.models import Employee, EmployeeVersion
from establishment.models import Position
from rbac_audit.consent import record_consent
from rbac_audit.models import ConsentRecord

from .models import Applicant, ApplicantStageEvent, Requisition
from .validation import ResumeValidationError, validate_resume_upload


class StageTransitionError(ValueError):
    pass


class DuplicateApplicationError(ValueError):
    """Raised (→ 400, not a raw IntegrityError → 500) when a careers-portal
    submission collides with the existing
    one_application_per_email_per_requisition constraint."""


def validate_requisition_positions(
    positions,
    *,
    headcount: int,
    requisition=None,
    requisition_department_id=None,
    requisition_location_id=None,
) -> None:
    """Raises ValueError (caught by the serializer, surfaced as a 400) if
    the linked positions don't satisfy C1's establishment-control rules.
    Already-linked positions (requisition.positions before this call) are
    exempt from the approved/vacant/unclaimed/same-place checks -- a
    position this SAME requisition already committed to stays valid even
    once one of its own hires has since filled it; only newly-added
    positions are held to the strict bar.

    requisition_department_id/requisition_location_id are what a new
    position must match. They're passed explicitly because on create there
    is no `requisition` instance yet to read them from; when a requisition
    IS given they default to its own. If neither source supplies one, that
    half of the cross-check is skipped rather than guessed at."""
    if requisition is not None:
        if requisition_department_id is None:
            requisition_department_id = requisition.department_id
        if requisition_location_id is None:
            requisition_location_id = requisition.location_id

    # Distinct ids, not len(positions): a payload naming the same position
    # twice ({"positions": [5, 5], "headcount": 2}) would satisfy a raw
    # length check while the M2M relation dedupes it to a single link,
    # silently leaving the requisition a position short.
    distinct_ids = {position.id for position in positions}
    if len(distinct_ids) != headcount:
        raise ValueError(
            f"{len(distinct_ids)} distinct position(s) linked but headcount is {headcount} -- they must match."
        )

    already_linked_ids = set(requisition.positions.values_list("id", flat=True)) if requisition else set()

    for position in positions:
        if position.id in already_linked_ids:
            continue
        if position.status != Position.Status.APPROVED:
            raise ValueError(f"Position {position.post_number} is not approved yet.")
        if not position.is_vacant:
            raise ValueError(f"Position {position.post_number} is not vacant.")
        # A requisition hires into its own department and location:
        # _complete_hire builds the new EmployeeVersion from the
        # REQUISITION's fields but stamps it with the POSITION, so a
        # mismatched link would persist a permanent version whose
        # department/location silently disagrees with its own post.
        if requisition_department_id is not None and position.department_id != requisition_department_id:
            raise ValueError(f"Position {position.post_number} belongs to a different department.")
        if requisition_location_id is not None and position.location_id != requisition_location_id:
            raise ValueError(f"Position {position.post_number} is at a different location.")
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

    # Which specific linked position does THIS hire consume? The
    # requisition's still-vacant linked positions, lowest post_number
    # first -- positions grouped into one requisition are by definition
    # interchangeable for this purpose (if they weren't, they'd belong in
    # separate requisitions). None for requisitions predating C1 (no
    # linked positions at all).
    position = (
        requisition.positions.filter(id__in=Position.objects.vacant().values("id"))
        .order_by("post_number")
        .first()
    )

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
                    position=position,
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


def backfill_requisition_positions() -> int:
    """One-time backfill (called from a migration): a CLOSED/FILLED
    requisition whose resulting hires now have backfilled Positions
    (establishment.services.backfill_positions_for_current_employees, run
    first) gets ALL of those positions linked -- a requisition can have
    several distinct hires (headcount > 1), each with their own 1:1
    backfilled Position, and all of them belong on this requisition, not
    just the first one found. Requisitions with no resulting hire predate
    establishment control entirely and stay unlinked. Idempotent:
    already-linked requisitions are skipped. Returns the count of
    requisitions backfilled (not positions linked).

    Called from migration 0004 via the live (not historical-state)
    Requisition model — `.only("id")` below is load-bearing, not just an
    optimisation: a fresh-database migration replay runs 0004 before any
    LATER migration that adds a Requisition column, so a query selecting
    every current field would reference a column that doesn't exist yet at
    that point in schema history (C6 surfaced this against `description`/
    `external_posting`). Restricting the SELECT to just the pk sidesteps it
    for any future field addition too, not only this one — nothing else in
    this loop reads a Requisition scalar field, only its relations."""
    linked = 0
    closed_statuses = [Requisition.Status.CLOSED, Requisition.Status.FILLED]
    for requisition in Requisition.objects.filter(status__in=closed_statuses).only("id"):
        if requisition.positions.exists():
            continue
        hired = requisition.applicants.filter(
            current_stage=Applicant.Stage.HIRED, resulting_employee__isnull=False
        ).select_related("resulting_employee")
        position_ids = {
            applicant.resulting_employee.current_version.position_id
            for applicant in hired
            if applicant.resulting_employee.current_version is not None
            and applicant.resulting_employee.current_version.position_id is not None
        }
        if position_ids:
            requisition.positions.add(*position_ids)
            linked += 1
    return linked


# --- C6: careers portal --------------------------------------------------
# Design spec §4.4. The one genuinely multi-step write among C6's new
# surfaces (validate -> create Applicant -> conditionally record consent ->
# conditionally set demographic fields, atomically) -- everything else in
# this slice (InterviewSession/InterviewScorecard/BackgroundCheck) is a
# single-row write validated in its own serializer, per the design spec's
# "no services.py for A-C" reasoning (§2.4).

@transaction.atomic
def submit_portal_application(
    *, requisition, first_name, last_name, email, phone, date_of_birth, resume,
    race="", gender="", disability_status="", demographic_consent=False,
) -> Applicant:
    """Raises ValueError (-> 400, never a 500) for a requisition that isn't
    open to public applications, a resume that fails content-sniffing or
    the size cap, or a duplicate email for this requisition. Spec §3.4.5:
    consent gates STORAGE of demographic answers, not submission of the
    application -- an unconsented demographic value is silently dropped,
    never a submission-blocking error."""
    if requisition.status != Requisition.Status.OPEN or not requisition.external_posting:
        raise ValueError("This requisition is not currently open for applications.")

    try:
        content_type = validate_resume_upload(resume)
    except ResumeValidationError as exc:
        raise ValueError(str(exc)) from exc

    try:
        with transaction.atomic():
            applicant = Applicant.objects.create(
                requisition=requisition, first_name=first_name, last_name=last_name, email=email,
                phone=phone or "", date_of_birth=date_of_birth, source=Applicant.Source.PORTAL,
                resume=resume, resume_content_type=content_type, resume_size_bytes=resume.size,
            )
    except IntegrityError as exc:
        raise DuplicateApplicationError(
            "An application for this position already exists for this email address."
        ) from exc

    if demographic_consent:
        record_consent(
            applicant=applicant, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1", actor=None,
        )
        update_fields = []
        if race:
            applicant.race = race
            update_fields.append("race")
        if gender:
            applicant.gender = gender
            update_fields.append("gender")
        if disability_status:
            applicant.disability_status = disability_status
            update_fields.append("disability_status")
        if update_fields:
            applicant.save(update_fields=update_fields)

    return applicant
