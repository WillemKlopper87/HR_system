from __future__ import annotations

from django.db import models
from simple_history.models import HistoricalRecords

from core_hr.base import TimestampedModel
from core_hr.models import Employee


class AssessmentAssignment(TimestampedModel):
    """Sensitive-tier (Data-Dictionary.md: "assessment_assignment (S)").
    Subject is an employee OR an applicant — the same duality as
    rbac_audit.ConsentRecord — but this module must not import
    recruitment.models (Architecture-Design.md §4: apps may import
    core_hr/rbac_audit only, never each other; the §4 module diagram draws
    no assessments->recruitment edge). applicant_id is therefore an
    unconstrained reference rather than a cross-app FK — safe in practice,
    since recruitment.Applicant rows are never hard-deleted (see
    recruitment/views.py::ApplicantViewSet). The frontend resolves
    applicant display data with its own direct fetch to /applicants/{id}/."""

    class AssessmentType(models.TextChoices):
        COGNITIVE = "cognitive", "Cognitive ability"
        PERSONALITY = "personality", "Personality profile"
        TECHNICAL = "technical", "Technical / skills test"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.CASCADE, related_name="assessment_assignments"
    )
    applicant_id = models.PositiveIntegerField(null=True, blank=True)

    assessment_type = models.CharField(max_length=20, choices=AssessmentType.choices)
    provider_key = models.CharField(max_length=50)
    provider_reference = models.CharField(max_length=200, blank=True)
    access_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ASSIGNED)

    assigned_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="assessments_assigned"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(employee__isnull=False, applicant_id__isnull=True)
                | models.Q(employee__isnull=True, applicant_id__isnull=False),
                name="assessmentassignment_exactly_one_subject",
            )
        ]

    def __str__(self):
        subject = self.employee.employee_number if self.employee_id else f"applicant #{self.applicant_id}"
        return f"{subject}: {self.get_assessment_type_display()} ({self.get_status_display()})"


class AssessmentResult(TimestampedModel):
    """Sensitive-tier (Data-Dictionary.md: "assessment_result (S)"). Kept
    as its own row rather than folded onto AssessmentAssignment — matching
    the Data Dictionary's explicit two-entity split — because a result
    only comes into existence once the provider's webhook reports
    completion; until then there's nothing to store."""

    assignment = models.OneToOneField(AssessmentAssignment, on_delete=models.CASCADE, related_name="result")
    raw_score = models.CharField(max_length=100, blank=True)
    summary = models.TextField(blank=True)
    detail = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result for assignment #{self.assignment_id}"


class ProviderConfig(TimestampedModel):
    """Internal-tier (Data-Dictionary.md: "provider_config (I)"). Which
    adapter is currently wired up (assessments/adapters/registry.py reads
    this, not a hardcoded import) — Architecture-Design.md §11: "Sprint 12
    acceptance criterion 'swap by reconfiguration' holds only if module
    code never imports a concrete adapter." `config` holds non-secret
    settings only (base URLs, timeouts); secrets stay in environment
    variables (Architecture-Design.md §8), never in this table."""

    provider_key = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=200)
    active = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["provider_key"]
        constraints = [
            models.UniqueConstraint(fields=["active"], condition=models.Q(active=True), name="one_active_provider"),
        ]

    def __str__(self):
        return f"{self.display_name} ({'active' if self.active else 'inactive'})"
