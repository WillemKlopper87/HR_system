from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from core_hr.base import TimestampedModel
from core_hr.models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel
from establishment.models import Position  # direct import: no cycle, establishment never imports recruitment back


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
    # C6 (careers portal design spec §2.5, §4.1): free-text job description
    # -- also useful for internal-only requisitions, not portal-exclusive.
    description = models.TextField(blank=True)
    # HR opts a requisition INTO public visibility; default False so every
    # existing requisition stays internal-only the moment this field ships.
    external_posting = models.BooleanField(default=False)
    # Which specific approved, vacant posts this requisition targets (C1) --
    # M2M, not a single FK: headcount can already be >1 (several identical
    # hires), so one requisition may claim several identical vacant posts
    # at once. See docs/superpowers/specs/2026-08-19-position-establishment-design.md §4.2.
    positions = models.ManyToManyField(Position, related_name="requisitions", blank=True)
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

    class Source(models.TextChoices):
        INTERNAL = "internal", "Internal"
        PORTAL = "portal", "Careers portal"

    requisition = models.ForeignKey(Requisition, on_delete=models.PROTECT, related_name="applicants")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField()
    current_stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.APPLIED)
    # C6 (careers portal design spec §2.5): provenance only -- never read by
    # the stage machine, retention handler, or hire flow. A portal-sourced
    # row is byte-for-byte the same kind of row an internal one is.
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.INTERNAL)
    # General, not portal-only: an internally-created applicant can also get
    # a CV attached via a recruiter PATCH. Server-sniffed (recruitment/
    # validation.py) -- never client-trusted, same discipline
    # documents.EmployeeDocument's content_type/size_bytes already use.
    resume = models.FileField(upload_to="applicant_resumes/%Y/%m/", null=True, blank=True)
    resume_content_type = models.CharField(max_length=120, blank=True)
    resume_size_bytes = models.PositiveIntegerField(default=0)
    rejected_reason = models.CharField(max_length=200, blank=True)
    # Set by recruitment/retention.py when a rejected applicant is anonymised
    # per RetentionRule; identifying fields are blanked, the row is kept for
    # aggregate reporting. Never set by the API.
    anonymised_at = models.DateTimeField(null=True, blank=True)

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


# --- C6: interview scheduling, panel scorecards, background checks --------
# Design spec: docs/superpowers/specs/2026-08-25-recruitment-interviews-careers-portal-design.md

# 1-5, matching performance's own rating vocabulary (performance/models/
# agreements.py RATING_MIN/MAX, performance/models/cycles.py RATING_CHOICES)
# -- duplicated as a plain tuple rather than imported: performance is an
# ordinary domain app (not kernel) and this is a constant, not a query, so
# there's no queries.py seam it could come through.
INTERVIEW_RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]


class InterviewSession(TimestampedModel):
    """One scheduled interview round for an applicant (spec §2.1). Plain M2M
    `interviewers` -- no through-model, since no per-panelist attribute is
    needed beyond "have they submitted a scorecard yet", which
    InterviewScorecard's own (session, interviewer) uniqueness already
    answers. Multiple rounds are just multiple rows, ordered by
    round_number -- no separate "round" object."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name="interview_sessions")
    round_number = models.PositiveSmallIntegerField(default=1)
    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60)
    # Free text: a room name or a video-call URL. No calendar integration.
    location = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    # Recruiter's own logistics/context notes -- distinct from a scorecard's
    # per-interviewer notes below.
    notes = models.TextField(blank=True)
    interviewers = models.ManyToManyField(Employee, related_name="interview_panels")
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="interview_sessions_created"
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["applicant", "round_number", "scheduled_at"]

    def __str__(self):
        return f"{self.applicant} — round {self.round_number} ({self.get_status_display()})"


class InterviewScorecard(TimestampedModel):
    """One interviewer's structured feedback for one session (spec §2.2).
    Fixed three-criterion vocabulary (not per-requisition configurable —
    see the spec for why); blind-review visibility (whether a viewer other
    than the author can see rating/comments/recommendation) is enforced in
    InterviewScorecardSerializer.to_representation, not here — the model
    itself carries no visibility state, only the data."""

    class Recommendation(models.TextChoices):
        STRONG_HIRE = "strong_hire", "Strong hire"
        HIRE = "hire", "Hire"
        NO_HIRE = "no_hire", "No hire"
        STRONG_NO_HIRE = "strong_no_hire", "Strong no hire"

    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="scorecards")
    interviewer = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="interview_scorecards")
    skill_rating = models.PositiveSmallIntegerField(choices=INTERVIEW_RATING_CHOICES)
    communication_rating = models.PositiveSmallIntegerField(choices=INTERVIEW_RATING_CHOICES)
    culture_fit_rating = models.PositiveSmallIntegerField(choices=INTERVIEW_RATING_CHOICES)
    comments = models.TextField(blank=True)
    recommendation = models.CharField(max_length=20, choices=Recommendation.choices)

    history = HistoricalRecords()

    class Meta:
        ordering = ["session", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["session", "interviewer"], name="one_scorecard_per_interviewer_per_session")
        ]

    def __str__(self):
        return f"{self.session}: {self.interviewer} — {self.get_recommendation_display()}"


class BackgroundCheck(TimestampedModel):
    """Tracking only, per docs/MVP-Backlog.md A3 #9 ("SA vetting is often
    manual/legal rather than API-shaped — low leverage") -- no vendor
    integration. No ALLOWED_TRANSITIONS state machine (unlike
    Applicant.Stage): a real vetting process can legitimately move
    non-monotonically (e.g. a flagged result revised to cleared after a
    documented review), so `status` is free-form, validated only for a
    legal enum value. Sensitive-tier by nature of the WHOLE model (spec
    §2.3) — gated by IsRecruiterOrHRAdmin at the endpoint level, same
    "whole-endpoint, not per-field" exception rbac_audit/tiers.py already
    documents for performance.Review/Feedback and succession.
    SuccessionCandidate."""

    class CheckType(models.TextChoices):
        REFERENCE = "reference", "Reference check"
        CRIMINAL_RECORD = "criminal_record", "Criminal record check"
        QUALIFICATION_VERIFICATION = "qualification_verification", "Qualification verification"
        CREDIT_CHECK = "credit_check", "Credit check"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        REQUESTED = "requested", "Requested"
        IN_PROGRESS = "in_progress", "In progress"
        CLEARED = "cleared", "Cleared"
        FLAGGED = "flagged", "Flagged"

    applicant = models.ForeignKey(Applicant, on_delete=models.CASCADE, related_name="background_checks")
    check_type = models.CharField(max_length=30, choices=CheckType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    requested_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="background_checks_requested"
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Outcome/context -- can legitimately hold criminal-record or
    # credit-check detail, hence the whole-model sensitivity gating above.
    notes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.applicant}: {self.get_check_type_display()} — {self.get_status_display()}"
