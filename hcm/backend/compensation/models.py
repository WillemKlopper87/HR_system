from __future__ import annotations

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core_hr.base import TimestampedModel
from core_hr.models import Department, Employee, JobGrade


class PayBandQuerySet(models.QuerySet):
    def as_at(self, as_of_date):
        return self.filter(valid_from__lte=as_of_date).filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gt=as_of_date)
        )

    def current(self):
        return self.as_at(timezone.localdate())


class PayBand(TimestampedModel):
    """Restricted-tier, effective-dated (Data-Dictionary.md: "pay_band
    (R, effective-dated)") — the same as_at()/current() pattern as
    core_hr.EmployeeVersion (Sprint 1 / ADR-002), applied to pay ranges
    instead of employee attributes. ADR-006: HCM masters pay bands and
    comp proposals; actual pay stays in SAP."""

    job_grade = models.ForeignKey(JobGrade, on_delete=models.PROTECT, related_name="pay_bands")
    min_salary = models.DecimalField(max_digits=12, decimal_places=2)
    mid_salary = models.DecimalField(max_digits=12, decimal_places=2)
    max_salary = models.DecimalField(max_digits=12, decimal_places=2)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="pay_bands_created"
    )

    objects = PayBandQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["job_grade", "-valid_from"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gt=models.F("valid_from")),
                name="payband_valid_to_after_valid_from",
            ),
            models.CheckConstraint(
                condition=models.Q(min_salary__lte=models.F("mid_salary"))
                & models.Q(mid_salary__lte=models.F("max_salary")),
                name="payband_min_mid_max_ordered",
            ),
        ]

    def __str__(self):
        return f"{self.job_grade.code}: {self.min_salary}-{self.max_salary} (from {self.valid_from})"

    def contains(self, salary) -> bool:
        return self.min_salary <= salary <= self.max_salary


class CompCycle(TimestampedModel):
    """A named salary-review/bonus round batching a set of CompProposal
    rows against one budget — design spec 2026-08-26 §2.1/§5.1.
    `CompProposal.cycle` is nullable: every proposal made before this
    existed, and every future ad-hoc one-off, keeps working exactly as
    before with no budget arithmetic in play. Flat currency `budget_amount`
    (not %-of-payroll, spec §2.2); `department=None` means org-wide, matching
    the brief's own "scope: org-wide or by department" wording rather than
    CourseRequirement's Department+OccupationalLevel two-axis shape (spec
    §2.3 — a comp cycle's budget doesn't need the cross-cut a training
    requirement's population does)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=200, unique=True)
    period_start = models.DateField()
    period_end = models.DateField()
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="comp_cycles"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="comp_cycles_created"
    )
    closed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="comp_cycles_closed"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-period_start"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_end__gt=models.F("period_start")),
                name="compcycle_period_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(budget_amount__gte=0), name="compcycle_budget_non_negative"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class CompProposal(TimestampedModel):
    """Restricted-tier (Data-Dictionary.md: "comp_proposal (R)"). Gated
    entirely by row-scope (compensation/permissions.py::IsCompManagerOrHRAdmin),
    not the generic tiered-serializer path — matches the sprint's own
    "Pay-data visibility restricted to comp manager/HR admin roles only
    (strict RBAC)" task literally, module-wide, catalog included.

    `proposal_type` distinguishes a salary increase from a bonus (design
    spec §2.4) rather than forking a second model — extends the one
    propose->approve->reject workflow instead of duplicating it.
    `proposed_annual_salary`/`bonus_amount` are each nullable and
    type-appropriate (constraint below); `cycle`/`exceeds_cycle_budget`/
    `baseline_salary_at_proposal` support batching proposals against a
    CompCycle's budget (spec §2.5) — all null/False when cycle is None,
    preserving the pre-existing one-off behaviour exactly."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class ProposalType(models.TextChoices):
        INCREASE = "increase", "Salary increase"
        BONUS = "bonus", "Bonus"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="comp_proposals")
    # Snapshotted at proposal time — the employee's grade (and therefore
    # which pay band applies) could change before this is approved.
    current_job_grade = models.ForeignKey(JobGrade, on_delete=models.PROTECT, related_name="comp_proposals")
    proposal_type = models.CharField(max_length=20, choices=ProposalType.choices, default=ProposalType.INCREASE)
    proposed_annual_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    bonus_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # RemunerationRecord.fixed_remuneration at proposal time (increase
    # proposals attached to a cycle only) — used to derive budget_impact
    # below without a live re-read of ee_reporting later. Same snapshot
    # posture as current_job_grade.
    baseline_salary_at_proposal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    justification = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    requires_override = models.BooleanField(default=False)
    exceeds_cycle_budget = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True)
    effective_date = models.DateField(null=True, blank=True)
    cycle = models.ForeignKey(
        CompCycle, null=True, blank=True, on_delete=models.PROTECT, related_name="proposals"
    )
    proposed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="comp_proposals_made"
    )
    approved_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="comp_proposals_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                # Nested Meta class bodies can't see CompProposal.ProposalType
                # by bare name (no enclosing-class scoping in Python for
                # nested classes) -- "increase"/"bonus" are the enum's own
                # values, not magic strings.
                condition=(
                    models.Q(
                        proposal_type="increase",
                        proposed_annual_salary__isnull=False,
                        bonus_amount__isnull=True,
                    )
                    | models.Q(
                        proposal_type="bonus",
                        bonus_amount__isnull=False,
                        proposed_annual_salary__isnull=True,
                    )
                ),
                name="comp_proposal_amount_matches_type",
            ),
        ]

    def __str__(self):
        amount = self.proposed_annual_salary if self.proposal_type == self.ProposalType.INCREASE else self.bonus_amount
        return f"{self.employee.employee_number}: {amount} ({self.get_status_display()})"

    @property
    def budget_impact(self):
        """The amount this proposal consumes from its cycle's budget, or
        None if that can't be computed (no cycle, or an increase with no
        baseline salary captured). A bonus consumes its whole amount; an
        increase consumes only the delta over the employee's baseline
        salary — a budget for raises isn't a budget for everyone's whole
        new payroll. Derived, not stored (design spec §2.5) — matches
        RemunerationRecord.total_remuneration's existing shape."""
        if self.proposal_type == self.ProposalType.BONUS:
            return self.bonus_amount
        if self.baseline_salary_at_proposal is None or self.proposed_annual_salary is None:
            return None
        return self.proposed_annual_salary - self.baseline_salary_at_proposal


class Benefit(TimestampedModel):
    """The benefits catalog. Gated the same as the rest of the module
    (comp_manager/hr_admin only) rather than treated as an open-read
    reference table like learning.Skill's catalog — this sprint's
    acceptance criterion is stricter, with no carve-out for catalog data."""

    class Category(models.TextChoices):
        MEDICAL = "medical", "Medical aid"
        RETIREMENT = "retirement", "Retirement fund"
        RISK_COVER = "risk_cover", "Risk cover (life/disability)"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class BenefitsElection(TimestampedModel):
    """Sensitive-tier (Data-Dictionary.md: "benefits_election (S)").
    Sprint 10 is HR/comp-admin *recording* elections, not employee self-
    service — self-service is Sprint 15's explicit task."""

    class Status(models.TextChoices):
        ENROLLED = "enrolled", "Enrolled"
        WAIVED = "waived", "Waived"
        PENDING = "pending", "Pending"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="benefits_elections")
    benefit = models.ForeignKey(Benefit, on_delete=models.PROTECT, related_name="elections")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    effective_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["employee", "benefit"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "benefit"], name="one_election_per_employee_per_benefit")
        ]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.benefit.name} ({self.status})"
