from __future__ import annotations

from core_hr.base import TimestampedModel
from core_hr.models import Employee, Location
from django.db import models
from simple_history.models import HistoricalRecords

from .constants import (
    BARRIER_CATEGORIES,
    BUSINESS_TYPES,
    DIFFERENTIAL_REASONS,
    EMPLOYEE_COUNT_BANDS,
    MONITORING_FREQUENCIES,
)


class EmployerConfig(TimestampedModel):
    """EEA2/EEA4 Section A identity fields — entered once, reused every
    year (EEA-Form-Spec-Notes.md #5). Editable; each generated EEReport
    snapshots a copy of these values into its own `data` JSON at
    generation time, so a later correction here doesn't retroactively
    change an already-generated report (Architecture-Design.md §5.1:
    "EE reporting reads from frozen snapshots")."""

    trade_name = models.CharField(max_length=200, blank=True)
    dti_registration_name = models.CharField(max_length=200, blank=True)
    dti_registration_number = models.CharField(max_length=100, blank=True)
    paye_sars_number = models.CharField(max_length=100, blank=True)
    uif_reference_number = models.CharField(max_length=100, blank=True)
    ee_reference_number = models.CharField(max_length=100, blank=True)
    national_or_provincial_eap = models.CharField(max_length=200, blank=True)
    industry_sector = models.CharField(max_length=200, blank=True)
    seta_classification = models.CharField(max_length=200, blank=True)
    bargaining_council = models.CharField(max_length=200, blank=True)
    telephone_number = models.CharField(max_length=50, blank=True)

    postal_address = models.TextField(blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    postal_city = models.CharField(max_length=100, blank=True)
    postal_province = models.CharField(max_length=3, choices=Location.Province.choices, blank=True)

    physical_address = models.TextField(blank=True)
    physical_code = models.CharField(max_length=20, blank=True)
    physical_city = models.CharField(max_length=100, blank=True)
    physical_province = models.CharField(max_length=3, choices=Location.Province.choices, blank=True)

    ceo_name = models.CharField(max_length=200, blank=True)
    ceo_telephone = models.CharField(max_length=50, blank=True)
    ceo_email = models.EmailField(blank=True)

    ee_senior_manager_name = models.CharField(max_length=200, blank=True)
    ee_senior_manager_telephone = models.CharField(max_length=50, blank=True)
    ee_senior_manager_email = models.EmailField(blank=True)

    business_type = models.CharField(max_length=60, choices=BUSINESS_TYPES, blank=True)
    # Sentech is an organ of state / SOE -> designated employer regardless
    # of headcount (EEA-Form-Spec-Notes.md, confirmed A1).
    is_organ_of_state = models.BooleanField(default=True)
    employee_count_band = models.CharField(max_length=20, choices=EMPLOYEE_COUNT_BANDS, blank=True)
    is_group_or_holding = models.BooleanField(default=False)
    group_name = models.CharField(max_length=200, blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return self.trade_name or "Employer configuration"


class EEPlan(TimestampedModel):
    """Section E: 5-year sector targets (top 4 levels) + numerical goals
    (semi/unskilled) + disability target, plus the annual-targets matrix
    for next year — aligned to the sector target timeframe
    (EEA-Form-Spec-Notes.md: 2025-2030 sector-target period)."""

    plan_period_start = models.DateField()
    plan_period_end = models.DateField()
    # {level_code: {"male": pct, "female": pct}} — TOP/SENIOR/PQ/SKILLED
    sector_targets = models.JSONField(default=dict, blank=True)
    # {level_code: {"male": pct, "female": pct}} — SEMI/UNSKILLED
    numerical_goals = models.JSONField(default=dict, blank=True)
    disability_5yr_target_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Full 10-column workforce matrix (see constants.py) for next year.
    annual_targets = models.JSONField(default=dict, blank=True)
    annual_target_disability_value = models.PositiveIntegerField(null=True, blank=True)
    annual_target_disability_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # {level_code: {column: pct}} — the applicable (national/provincial) EAP
    # the plan was set against (EE Regs 2025 reg. 9(5) mandatory input).
    # Progress snapshots flag over-representation above it (reg. 9(10)-(11)).
    eap_profile = models.JSONField(default=dict, blank=True)

    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="ee_plans_created"
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["-plan_period_start"]

    def __str__(self):
        return f"EE Plan {self.plan_period_start}–{self.plan_period_end}"


class RemunerationRecord(TimestampedModel):
    """EEA4's hard dependency (EEA-Form-Spec-Notes.md #1) — annualised
    fixed + variable remuneration per employee per reporting period. No
    real SAP payroll integration exists yet (ADR-006 notes this as a
    future Sprint 12b interface) — populated via CSV import
    (services.py::import_remuneration_csv), the same "build the seam,
    defer the vendor" pattern as assessments/identity_verification.
    Amounts are whole Rand (spec: "no separators or decimals")."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="remuneration_records")
    period_start = models.DateField()
    period_end = models.DateField()
    fixed_remuneration = models.PositiveIntegerField()
    variable_remuneration = models.PositiveIntegerField(default=0)
    imported_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="remuneration_records_imported"
    )

    class Meta:
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "period_start", "period_end"], name="one_remuneration_record_per_employee_per_period"
            )
        ]

    @property
    def total_remuneration(self) -> int:
        return self.fixed_remuneration + self.variable_remuneration

    def __str__(self):
        return f"{self.employee.employee_number}: R{self.total_remuneration} ({self.period_start}–{self.period_end})"


class EEQuestionnaire(TimestampedModel):
    """The parts of EEA2/EEA4 that aren't computed from other modules'
    data — Sections B(cont.)/F/G narrative answers on EEA2, Section E
    narrative on EEA4. One per report_year (both forms for that year
    share the same questionnaire, matching "submitted together")."""

    report_year = models.PositiveIntegerField(unique=True)

    achieved_all_targets = models.BooleanField(null=True)
    # {row_key: [reason_key, ...]} — row_key is an occupational level code or "disability".
    justifiable_reasons = models.JSONField(default=dict, blank=True)
    # {stakeholder_key: bool}
    consultation = models.JSONField(default=dict, blank=True)
    # {category_key: {"barriers": bool, "aa_measures": bool, "start_date": "YYYY-MM-DD"|None, "end_date": ...}}
    barriers = models.JSONField(default=dict, blank=True)
    monitoring_frequency = models.CharField(max_length=20, choices=MONITORING_FREQUENCIES, blank=True)
    achieved_annual_objectives = models.BooleanField(null=True)
    achieved_annual_objectives_explanation = models.TextField(blank=True)

    # EEA4 Section E narrative
    has_remuneration_policy = models.BooleanField(null=True)
    remuneration_gap_aligned_to_policy = models.BooleanField(null=True)
    has_measures_in_ee_plan = models.BooleanField(null=True)
    differential_reason = models.CharField(max_length=40, choices=DIFFERENTIAL_REASONS, blank=True)
    differential_reason_other = models.TextField(blank=True)
    vertical_gap_multiple = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    updated_by = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    history = HistoricalRecords()

    class Meta:
        ordering = ["-report_year"]

    def __str__(self):
        return f"EE Questionnaire {self.report_year}"


class EEReport(TimestampedModel):
    """A frozen, versioned EEA2 or EEA4 draft/submission —
    Architecture-Design.md §5.1: "generating an EEA2/EEA4 draft
    materialises an immutable snapshot table... a later data fix never
    silently changes a signed report." Never edited in place after
    generation — re-generating creates a new version
    (services.py::generate_report); the previous version's status flips
    to SUPERSEDED rather than being deleted, preserving the archive."""

    class FormType(models.TextChoices):
        EEA2 = "eea2", "EEA2"
        EEA4 = "eea4", "EEA4"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_EE_REVIEW = "pending_ee_review", "Pending EE manager review"
        PENDING_SIGNOFF = "pending_signoff", "Pending Accounting Officer sign-off"
        SIGNED_OFF = "signed_off", "Signed off"
        SUPERSEDED = "superseded", "Superseded by a later version"

    form_type = models.CharField(max_length=10, choices=FormType.choices)
    report_year = models.PositiveIntegerField()
    version = models.PositiveIntegerField()
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    data = models.JSONField()

    generated_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="ee_reports_generated"
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    ee_reviewed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="ee_reports_reviewed"
    )
    ee_reviewed_at = models.DateTimeField(null=True, blank=True)
    signed_off_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="ee_reports_signed_off"
    )
    signed_off_at = models.DateTimeField(null=True, blank=True)
    signed_off_place = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-report_year", "form_type", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["form_type", "report_year", "version"], name="unique_report_version"),
        ]

    def __str__(self):
        return f"{self.get_form_type_display()} {self.report_year} v{self.version} ({self.get_status_display()})"


# --- C6: EE plan depth + consultation-forum records (design spec
# docs/superpowers/specs/2026-08-26-ee-plan-consultation-forum-design.md).
# Everything below exists to put evidence behind Section F's bare Y/N
# answers and Section E's targets: who consulted, when, what the plan's
# measures actually are, and how the numerical goals have tracked.


class EEForumMember(TimestampedModel):
    """One seat on the EE consultative forum (EEA s.16). `representation`
    is the s.16(1) consulting party the member speaks for; occupational
    level and designated-group status are deliberately NOT stored here —
    they're derived from the member's current EmployeeVersion at check
    time (services.py::forum_composition), so a promotion or a demographic
    correction never leaves a stale copy behind. `union_nominated` reveals
    trade-union affiliation — POPIA s.26 special personal information, so
    the serializer redacts `representation`/`notes` for anyone reading
    through the member carve-out rather than an EE role (spec §5)."""

    class Representation(models.TextChoices):
        UNION_NOMINATED = "union_nominated", "Nominated by a representative trade union"
        EMPLOYEE_NOMINATED = "employee_nominated", "Nominated by employees"
        EMPLOYER = "employer", "Employer / management representative"

    class Role(models.TextChoices):
        CHAIR = "chair", "Chairperson"
        SECRETARY = "secretary", "Secretary"
        MEMBER = "member", "Member"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="ee_forum_memberships")
    representation = models.CharField(max_length=20, choices=Representation.choices)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    term_start = models.DateField()
    term_end = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-term_start", "employee__employee_number"]

    def is_active_on(self, day) -> bool:
        return self.term_start <= day and (self.term_end is None or self.term_end >= day)

    def __str__(self):
        return f"{self.employee.employee_number} ({self.get_role_display()}, from {self.term_start})"


class EEForumMeeting(TimestampedModel):
    """A sitting of the forum. `report_year` is matched by value against
    EEQuestionnaire.report_year (not an FK — the first meeting of a year is
    usually minuted before that year's questionnaire exists). Attendance is
    an M2M to members so it's factual, never a typed-in count. Minutes are
    content-sniffed on upload (uploads.py) and served only through the
    authenticated download action, never a raw MEDIA_URL."""

    meeting_date = models.DateField()
    title = models.CharField(max_length=200)
    report_year = models.PositiveIntegerField()
    agenda = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    resolutions = models.TextField(blank=True)
    attendees = models.ManyToManyField(EEForumMember, related_name="meetings_attended", blank=True)
    minutes_file = models.FileField(upload_to="ee_forum_minutes/%Y/%m/", null=True, blank=True)
    minutes_content_type = models.CharField(max_length=120, blank=True)
    minutes_sha256 = models.CharField(max_length=64, blank=True)
    recorded_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="ee_forum_meetings_recorded"
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["-meeting_date"]

    def __str__(self):
        return f"{self.meeting_date}: {self.title}"


class EEPlanMeasure(TimestampedModel):
    """One barrier + affirmative-action measure on the plan, per EEA13:
    every measure carries a responsible person and a time frame inside the
    plan period (both required — reg. 9 / EEA13 template), which is what
    turns the questionnaire's per-category Y/N into something an
    inspector can follow up. `category` keys BARRIER_CATEGORIES (the 24
    fixed Section F rows; count untouched)."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        ABANDONED = "abandoned", "Abandoned"

    plan = models.ForeignKey(EEPlan, on_delete=models.CASCADE, related_name="measures")
    category = models.CharField(max_length=60, choices=BARRIER_CATEGORIES)
    barrier_description = models.TextField(blank=True)
    measure_description = models.TextField()
    owner = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="ee_plan_measures_owned")
    target_start = models.DateField()
    target_end = models.DateField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PLANNED)
    progress_notes = models.TextField(blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["plan", "category", "target_end"]

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone

        return (
            self.status in (self.Status.PLANNED, self.Status.IN_PROGRESS)
            and self.target_end < timezone.localdate()
        )

    def __str__(self):
        return f"{self.get_category_display()}: {self.measure_description[:40]}"


class EEPlanProgressSnapshot(TimestampedModel):
    """Point-in-time actual-vs-target for the plan (spec §4.2) — the one
    place storing beats deriving: EmployeeVersion history is corrected
    retroactively and subject to retention, so a recomputation years into
    the plan period is neither cheap nor guaranteed to reproduce what the
    forum actually tabled. Matrices are stored UNSUPPRESSED (same as
    EEReport.data) and suppressed per requester on read. Create-only."""

    plan = models.ForeignKey(EEPlan, on_delete=models.CASCADE, related_name="progress_snapshots")
    as_of = models.DateField()
    workforce_profile = models.JSONField(default=dict)
    disability_workforce = models.JSONField(default=dict)
    # Percentage-point gaps (actual - target), per level x column, against
    # the plan's own annual targets (reg. 9(13): compliance is assessed
    # against these), the 5-year sector targets / numerical goals, and the
    # EAP (reg. 9(10)-(11): over-representation above EAP is a finding too).
    annual_target_gap_pct = models.JSONField(default=dict)
    sector_target_gap_pct = models.JSONField(default=dict)
    eap_gap_pct = models.JSONField(default=dict)
    # {level: {"male": pct, "female": pct, "total": pct}} — designated-group
    # share of the level, the shape the sector-target gazette uses.
    designated_group_pct = models.JSONField(default=dict)
    disability_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # [{"row", "col", "basis", "gap_pct"}] — shortfalls vs annual target and
    # over-representation vs EAP, both directions, so the forum sees them
    # without re-reading three matrices.
    flags = models.JSONField(default=list)
    note = models.CharField(max_length=300, blank=True)
    taken_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="ee_plan_snapshots_taken"
    )

    class Meta:
        ordering = ["-as_of"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "as_of"], name="one_ee_plan_snapshot_per_day"),
        ]

    def __str__(self):
        return f"Snapshot {self.as_of} for {self.plan}"
