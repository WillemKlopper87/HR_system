from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from core_hr.base import TimestampedModel
from core_hr.models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel


class Requisition(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        ON_HOLD = "on_hold", "On hold"
        CLOSED = "closed", "Closed"
        FILLED = "filled", "Filled"

    title = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="requisitions")
    occupational_level = models.ForeignKey(
        OccupationalLevel, on_delete=models.PROTECT, related_name="requisitions"
    )
    job_grade = models.ForeignKey(
        JobGrade, null=True, blank=True, on_delete=models.PROTECT, related_name="requisitions"
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="requisitions")
    headcount = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    hiring_manager = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="requisitions_managed"
    )
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="requisitions_created"
    )
    opened_at = models.DateField(null=True, blank=True)
    target_fill_date = models.DateField(null=True, blank=True)
    closed_at = models.DateField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.department.code}) — {self.get_status_display()}"

    @property
    def hired_count(self) -> int:
        return self.applicants.filter(current_stage=Applicant.Stage.HIRED).count()


class Applicant(TimestampedModel):
    class Stage(models.TextChoices):
        APPLIED = "applied", "Applied"
        SCREENED = "screened", "Screened"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"
        HIRED = "hired", "Hired"
        REJECTED = "rejected", "Rejected"

    # Forward-only pipeline, plus "rejected" reachable from any active stage.
    ALLOWED_TRANSITIONS = {
        Stage.APPLIED: {Stage.SCREENED, Stage.REJECTED},
        Stage.SCREENED: {Stage.INTERVIEW, Stage.REJECTED},
        Stage.INTERVIEW: {Stage.OFFER, Stage.REJECTED},
        Stage.OFFER: {Stage.HIRED, Stage.REJECTED},
        Stage.HIRED: set(),
        Stage.REJECTED: set(),
    }

    requisition = models.ForeignKey(Requisition, on_delete=models.PROTECT, related_name="applicants")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField()
    current_stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.APPLIED)
    rejected_reason = models.CharField(max_length=200, blank=True)

    # Sensitive-tier, consent-gated (Data-Dictionary.md: "applicant (S —
    # demographics, consent-gated)"; RBAC-Roles.md recruiter note). Reuses
    # core_hr.EmployeeVersion's choice sets rather than redefining the
    # same enums a second time.
    race = models.CharField(
        max_length=20, choices=EmployeeVersion.Race.choices, default=EmployeeVersion.Race.NOT_DISCLOSED
    )
    gender = models.CharField(
        max_length=20, choices=EmployeeVersion.Gender.choices, default=EmployeeVersion.Gender.NOT_DISCLOSED
    )
    disability_status = models.CharField(
        max_length=20,
        choices=EmployeeVersion.DisabilityStatus.choices,
        default=EmployeeVersion.DisabilityStatus.NOT_DISCLOSED,
    )

    resulting_employee = models.OneToOneField(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="applicant_record"
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["requisition", "email"], name="one_application_per_email_per_requisition"
            )
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} — {self.get_current_stage_display()}"

    def can_transition_to(self, stage: str) -> bool:
        return stage in self.ALLOWED_TRANSITIONS.get(self.current_stage, set())


class ApplicantStageEvent(TimestampedModel):
    """Audit trail of pipeline movement — also what the recruitment
    dashboard's time-to-fill / time-in-stage metrics are computed from."""

    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name="stage_events")
    from_stage = models.CharField(max_length=20, choices=Applicant.Stage.choices, blank=True)
    to_stage = models.CharField(max_length=20, choices=Applicant.Stage.choices)
    changed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="applicant_stage_events_changed"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["applicant", "created_at"]

    def __str__(self):
        return f"{self.applicant_id}: {self.from_stage or '(new)'} -> {self.to_stage}"


class Offer(TimestampedModel):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        WITHDRAWN = "withdrawn", "Withdrawn"

    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name="offers")
    proposed_job_grade = models.ForeignKey(JobGrade, on_delete=models.PROTECT, related_name="offers")
    # Restricted-tier (Data-Dictionary.md: "offer (R — pay)"). RBAC-Roles.md
    # gives recruiter a narrow exception here ("offer pay: RW within band")
    # despite recruiter's generic R-tier grant being closed — enforced by
    # gating the whole endpoint to recruiter/hr_admin (IsRecruiterOrHRAdmin)
    # rather than layering the generic field-tier machinery on top.
    proposed_annual_salary = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    proposed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="offers_proposed"
    )
    approved_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="offers_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Offer for {self.applicant} ({self.get_status_display()})"
