from __future__ import annotations

from core_hr.base import TimestampedModel
from core_hr.models import Employee, Location
from django.db import models
from simple_history.models import HistoricalRecords

from .constants import BUSINESS_TYPES, DIFFERENTIAL_REASONS, EMPLOYEE_COUNT_BANDS, MONITORING_FREQUENCIES


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
