from __future__ import annotations

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core_hr.base import TimestampedModel
from core_hr.models import Employee, JobGrade


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


class CompProposal(TimestampedModel):
    """Restricted-tier (Data-Dictionary.md: "comp_proposal (R)"). Gated
    entirely by row-scope (compensation/permissions.py::IsCompManagerOrHRAdmin),
    not the generic tiered-serializer path — matches the sprint's own
    "Pay-data visibility restricted to comp manager/HR admin roles only
    (strict RBAC)" task literally, module-wide, catalog included."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="comp_proposals")
    # Snapshotted at proposal time — the employee's grade (and therefore
    # which pay band applies) could change before this is approved.
    current_job_grade = models.ForeignKey(JobGrade, on_delete=models.PROTECT, related_name="comp_proposals")
    proposed_annual_salary = models.DecimalField(max_digits=12, decimal_places=2)
    justification = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    requires_override = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True)
    effective_date = models.DateField(null=True, blank=True)
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

    def __str__(self):
        return f"{self.employee.employee_number}: {self.proposed_annual_salary} ({self.get_status_display()})"


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
