"""Performance agreements / KPI contracting (PC-1, ADR-010).

Mirrors the actual FY scorecard workbook (see KPI-Contracting-Investigation.md
§2a): a *period* (financial year 1 Apr–31 Mar) with three phases —
contracting, mid-year (Q2), final (Q4) — a versioned, targeted *template* of
Objective → KPA → KPI rows (weight per KPI, Σ = 1.00, one target descriptor per
rating level 1–5), one *agreement* per employee per period instantiated from
the template, strict employee-then-Head *signatures* per stage with a hashed
PDF snapshot, explicit dated *delegation* of the Head's signing authority, and
a *reminder log* so the scheduled push (ADR-011) is idempotent.

Kept deliberately separate from the legacy single-rating `ReviewCycle`/`Review`
(cycles.py): `PerformancePeriod.legacy_cycle` links the two so PC-2 can derive
the old rating from the agreement while the old pages still exist.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords

from core_hr.base import TimestampedModel
from core_hr.models import Department, Employee, JobGrade, OccupationalLevel

RATING_MIN, RATING_MAX = 1, 5
DEFAULT_RATING_SCALE = {
    "1": "Below Target",
    "2": "Partially meets target",
    "3": "On Target",
    "4": "Stretch Target",
    "5": "Exceeded Stretch Target",
}
DEFAULT_REMINDER_OFFSETS = [28, 14, 7, 1]


class PerformancePeriod(TimestampedModel):
    """One financial year of performance contracting (1 Apr → 31 Mar)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONTRACTING = "contracting", "Contracting open"
        ACTIVE = "active", "Active (contracted)"
        MIDYEAR = "midyear", "Mid-year review open"
        FINAL = "final", "Final assessment open"
        CLOSED = "closed", "Closed"
        ARCHIVED = "archived", "Archived"

    name = models.CharField(max_length=20, unique=True, help_text="e.g. 2026/27")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="performance_periods_created"
    )
    # Bridge to the Sprint 6-7 single-rating cycle so PC-2 can derive
    # Review.self_rating/manager_rating from the agreement's final score.
    legacy_cycle = models.OneToOneField(
        "performance.ReviewCycle", null=True, blank=True, on_delete=models.SET_NULL, related_name="performance_period"
    )
    # Threshold below which an agreement's final score raises hr_attention
    # (user: 3 = doing the job). Per-KPI flagging is a PC-2 option.
    attention_threshold = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("3.00"))

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"Performance period {self.name} ({self.get_status_display()})"

    def phase(self, stage: str) -> "PeriodPhase | None":
        return self.phases.filter(stage=stage).first()


class PeriodPhase(TimestampedModel):
    """A stage window inside a period plus its reminder schedule."""

    class Stage(models.TextChoices):
        CONTRACTING = "contracting", "Contracting"
        MIDYEAR = "midyear", "Mid-year review (Q2)"
        FINAL = "final", "Final assessment (Q4)"

    period = models.ForeignKey(PerformancePeriod, on_delete=models.CASCADE, related_name="phases")
    stage = models.CharField(max_length=20, choices=Stage.choices)
    opens_on = models.DateField()
    due_on = models.DateField()
    # Days before due_on at which a reminder goes out; overdue reminders repeat
    # every `overdue_every_days` after due_on until the step is done.
    reminder_offsets_days = models.JSONField(default=list)
    overdue_every_days = models.PositiveSmallIntegerField(default=7)

    class Meta:
        ordering = ["period", "opens_on"]
        constraints = [models.UniqueConstraint(fields=["period", "stage"], name="one_phase_per_stage_per_period")]

    def __str__(self):
        return f"{self.period.name} {self.get_stage_display()} ({self.opens_on} → {self.due_on})"

    def save(self, *args, **kwargs):
        if not self.reminder_offsets_days:
            self.reminder_offsets_days = list(DEFAULT_REMINDER_OFFSETS)
        super().save(*args, **kwargs)


class AgreementTemplate(TimestampedModel):
    """Versioned scorecard layout for a period / population."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    class SignatureMethod(models.TextChoices):
        PASSWORD = "password_reauth", "Click-to-sign with password re-authentication"
        TOTP = "totp_stepup", "Click-to-sign with authenticator (TOTP) step-up"

    name = models.CharField(max_length=200)
    version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    period = models.ForeignKey(
        PerformancePeriod, null=True, blank=True, on_delete=models.SET_NULL, related_name="templates",
        help_text="Optional: pin to one period; blank = reusable across periods",
    )
    rating_scale = models.JSONField(default=dict)
    evidence_required = models.BooleanField(default=False)
    signature_method = models.CharField(max_length=20, choices=SignatureMethod.choices, default=SignatureMethod.PASSWORD)
    # Targeting (any-of within each set; all sets empty = everyone)
    job_grades = models.ManyToManyField(JobGrade, blank=True, related_name="agreement_templates")
    occupational_levels = models.ManyToManyField(OccupationalLevel, blank=True, related_name="agreement_templates")
    departments = models.ManyToManyField(Department, blank=True, related_name="agreement_templates")
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="agreement_templates_created"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name", "-version"]
        constraints = [models.UniqueConstraint(fields=["name", "version"], name="unique_template_name_version")]

    def __str__(self):
        return f"{self.name} v{self.version} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.rating_scale:
            self.rating_scale = dict(DEFAULT_RATING_SCALE)
        super().save(*args, **kwargs)

    def applies_to(self, employee: Employee) -> bool:
        version = employee.current_version
        if self.job_grades.exists() and (version is None or version.job_grade_id not in set(self.job_grades.values_list("id", flat=True))):
            return False
        if self.occupational_levels.exists() and (
            version is None or version.occupational_level_id not in set(self.occupational_levels.values_list("id", flat=True))
        ):
            return False
        if self.departments.exists() and (
            version is None or version.department_id not in set(self.departments.values_list("id", flat=True))
        ):
            return False
        return True


class TemplateSection(TimestampedModel):
    """The FY's Objectives / Perspectives — the top-level grouping with a
    weight sub-total. Locked = cascaded from the corporate scorecard."""

    template = models.ForeignKey(AgreementTemplate, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)
    locked = models.BooleanField(default=True)

    class Meta:
        ordering = ["template", "order", "id"]

    def __str__(self):
        return self.title


class TemplateElement(TimestampedModel):
    """One KPI row of the template: KPA + KPI + metric + default weight + the
    per-level target descriptors (the workbook's 5 target columns)."""

    template = models.ForeignKey(AgreementTemplate, on_delete=models.CASCADE, related_name="elements")
    section = models.ForeignKey(TemplateSection, on_delete=models.CASCADE, related_name="elements")
    kpa_description = models.CharField(max_length=300)
    kpi_title = models.CharField(max_length=300)
    metric = models.CharField(max_length=100, blank=True)
    default_weight = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0"))
    level_descriptors = models.JSONField(default=dict, help_text='{"1": "...", ..., "5": "..."}')
    order = models.PositiveSmallIntegerField(default=0)
    locked = models.BooleanField(default=False)

    class Meta:
        ordering = ["template", "section__order", "order", "id"]

    def __str__(self):
        return self.kpi_title


class PerformanceAgreement(TimestampedModel):
    """One employee's scorecard for one period. `head` is snapshotted from the
    org chart at creation (like Review.manager) so a mid-year reporting change
    doesn't silently reassign who signs."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted to Head"
        RETURNED = "returned", "Returned for changes"
        APPROVED = "approved", "Approved — awaiting employee signature"
        EMPLOYEE_SIGNED = "employee_signed", "Employee signed — awaiting Head signature"
        AGREED = "agreed", "Agreed (contracted)"
        MIDYEAR_OPEN = "midyear_open", "Mid-year review open"
        MIDYEAR_EMPLOYEE_SIGNED = "midyear_employee_signed", "Mid-year: employee signed"
        MIDYEAR_SIGNED = "midyear_signed", "Mid-year review signed"
        FINAL_OPEN = "final_open", "Final assessment open"
        FINAL_EMPLOYEE_SIGNED = "final_employee_signed", "Final: employee signed"
        FINAL_SIGNED = "final_signed", "Final assessment signed"
        ARCHIVED = "archived", "Archived"

    # Statuses in which the contracting content (elements/PDP) may still change.
    EDITABLE_STATUSES = (Status.DRAFT, Status.RETURNED)
    CONTRACTED_STATUSES = (
        Status.AGREED, Status.MIDYEAR_OPEN, Status.MIDYEAR_EMPLOYEE_SIGNED, Status.MIDYEAR_SIGNED,
        Status.FINAL_OPEN, Status.FINAL_EMPLOYEE_SIGNED, Status.FINAL_SIGNED, Status.ARCHIVED,
    )

    period = models.ForeignKey(PerformancePeriod, on_delete=models.PROTECT, related_name="agreements")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="performance_agreements")
    head = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="performance_agreements_as_head"
    )
    template = models.ForeignKey(AgreementTemplate, on_delete=models.PROTECT, related_name="agreements")
    template_version = models.PositiveSmallIntegerField()
    revision = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    return_reason = models.TextField(blank=True)
    amendment_reason = models.TextField(blank=True)
    final_score = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    hr_attention = models.BooleanField(default=False)
    hr_attention_reason = models.CharField(max_length=300, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    agreed_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-period__start_date", "employee"]
        constraints = [models.UniqueConstraint(fields=["period", "employee"], name="one_agreement_per_employee_per_period")]

    def __str__(self):
        return f"{self.employee.employee_number} — {self.period.name} rev{self.revision} ({self.get_status_display()})"

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    @property
    def total_weight(self) -> Decimal:
        return sum((e.weight for e in self.elements.all()), Decimal("0"))

    @property
    def current_stage(self) -> str:
        s = self.status
        if s.startswith("midyear"):
            return PeriodPhase.Stage.MIDYEAR
        if s.startswith("final") or s == self.Status.ARCHIVED:
            return PeriodPhase.Stage.FINAL
        return PeriodPhase.Stage.CONTRACTING


class AgreementElement(TimestampedModel):
    """One KPI row on an agreement (copied from the template, then editable
    while the agreement is in DRAFT/RETURNED)."""

    agreement = models.ForeignKey(PerformanceAgreement, on_delete=models.CASCADE, related_name="elements")
    section_title = models.CharField(max_length=200)
    section_order = models.PositiveSmallIntegerField(default=0)
    kpa_description = models.CharField(max_length=300)
    kpi_title = models.CharField(max_length=300)
    metric = models.CharField(max_length=100, blank=True)
    weight = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0"))
    level_descriptors = models.JSONField(default=dict)
    order = models.PositiveSmallIntegerField(default=0)
    locked = models.BooleanField(default=False)
    # Q2 (mid-year) — PC-2 fills these in
    q2_target_note = models.TextField(blank=True)
    q2_employee_comment = models.TextField(blank=True)
    q2_head_comment = models.TextField(blank=True)
    # Q4 (final) — PC-2
    final_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(RATING_MIN), MaxValueValidator(RATING_MAX)]
    )
    final_employee_comment = models.TextField(blank=True)
    final_head_comment = models.TextField(blank=True)

    class Meta:
        ordering = ["agreement", "section_order", "order", "id"]

    def __str__(self):
        return f"{self.kpi_title} ({self.weight})"

    @property
    def score(self) -> Decimal | None:
        if self.final_rating is None:
            return None
        return (Decimal(self.final_rating) * self.weight).quantize(Decimal("0.0001"))


class PDPItem(TimestampedModel):
    """Personal Development Plan row (the workbook's PDP sheet)."""

    agreement = models.ForeignKey(PerformanceAgreement, on_delete=models.CASCADE, related_name="pdp_items")
    business_process = models.CharField(max_length=300)
    course_or_training = models.CharField(max_length=300)
    order = models.PositiveSmallIntegerField(default=0)
    # Optional link to a learning request the employee raised for it (via
    # learning's own endpoint — no cross-app import here, unconstrained id).
    training_record_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["agreement", "order", "id"]


class SigningDelegation(TimestampedModel):
    """A Head hands signing authority to a designated person for a date range
    (user: 'a person designated by the boss has authority'). Created by the
    Head or by hr_admin; audit-logged; the signature record shows both."""

    delegator = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="signing_delegations_given")
    delegate = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="signing_delegations_received")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="signing_delegations_created"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.delegator.employee_number} → {self.delegate.employee_number} ({self.start_date}–{self.end_date})"

    def is_active_on(self, day) -> bool:
        return self.revoked_at is None and self.start_date <= day <= self.end_date


class AgreementDocument(TimestampedModel):
    """The PDF snapshot of the agreement at a stage/revision — what actually
    gets signed (its sha256 is recorded on each signature) and archived."""

    agreement = models.ForeignKey(PerformanceAgreement, on_delete=models.CASCADE, related_name="documents")
    stage = models.CharField(max_length=20, choices=PeriodPhase.Stage.choices)
    revision = models.PositiveSmallIntegerField()
    pdf = models.FileField(upload_to="performance_agreements/%Y/%m/")
    sha256 = models.CharField(max_length=64)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at"]
        constraints = [
            models.UniqueConstraint(fields=["agreement", "stage", "revision"], name="one_document_per_stage_revision")
        ]


class AgreementSignature(TimestampedModel):
    """Immutable record of a click-to-sign act (ECT Act ordinary electronic
    signature): who, acting for whom, when, how it was proven, on which exact
    document (sha256). No update/delete path exists in the API."""

    class Role(models.TextChoices):
        EMPLOYEE = "employee", "Employee"
        HEAD = "head", "Head / executive"

    class Method(models.TextChoices):
        PASSWORD = "password_reauth", "Password re-authentication"
        TOTP = "totp_stepup", "Authenticator (TOTP) step-up"

    agreement = models.ForeignKey(PerformanceAgreement, on_delete=models.CASCADE, related_name="signatures")
    stage = models.CharField(max_length=20, choices=PeriodPhase.Stage.choices)
    revision = models.PositiveSmallIntegerField()
    role = models.CharField(max_length=20, choices=Role.choices)
    signer = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="agreement_signatures")
    acting_for = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT, related_name="agreement_signatures_delegated"
    )
    signed_at = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=20, choices=Method.choices)
    document = models.ForeignKey(AgreementDocument, on_delete=models.PROTECT, related_name="signatures")
    document_sha256 = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["signed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["agreement", "stage", "revision", "role"], name="one_signature_per_role_per_stage_revision"
            )
        ]

    def __str__(self):
        who = self.signer.employee_number + (f" for {self.acting_for.employee_number}" if self.acting_for_id else "")
        return f"{self.get_role_display()} signature by {who} on {self.agreement} [{self.stage}]"


class ReminderLog(TimestampedModel):
    """One row per reminder actually emitted (or intentionally recorded when
    no channel is enabled), keyed so the daily job is idempotent."""

    class Kind(models.TextChoices):
        EMPLOYEE_ITEM = "employee_item", "Employee to-do"
        HEAD_DIGEST = "head_digest", "Head digest"
        ANNOUNCEMENT = "announcement", "Phase announcement"

    period = models.ForeignKey(PerformancePeriod, on_delete=models.CASCADE, related_name="reminder_logs")
    stage = models.CharField(max_length=20, choices=PeriodPhase.Stage.choices)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # Unique idempotency key, e.g. "2026/27:contracting:employee_item:E0042:T-14"
    key = models.CharField(max_length=200, unique=True)
    employee = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.CASCADE, related_name="reminder_logs")
    agreement = models.ForeignKey(
        PerformanceAgreement, null=True, blank=True, on_delete=models.CASCADE, related_name="reminder_logs"
    )
    offset_days = models.IntegerField(null=True, blank=True, help_text="days before due (negative = overdue)")
    channel = models.CharField(max_length=20, default="collab")
    external_ref = models.CharField(max_length=200, blank=True)
    detail = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        indexes = [models.Index(fields=["period", "stage", "kind"])]
