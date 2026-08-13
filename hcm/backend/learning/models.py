from __future__ import annotations

from django.db import models
from django.utils import timezone

from core_hr.base import TimestampedModel
from core_hr.models import Employee


class Skill(TimestampedModel):
    """Public-tier (Data-Dictionary.md) — the catalog itself isn't
    sensitive; only who holds which skill (EmployeeSkill) carries any
    access consideration, and that's Internal, not Sensitive."""

    class Category(models.TextChoices):
        TECHNICAL = "technical", "Technical"
        SOFT = "soft", "Soft skill"
        LEADERSHIP = "leadership", "Leadership"
        COMPLIANCE = "compliance", "Compliance"
        OTHER = "other", "Other"

    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class EmployeeSkill(TimestampedModel):
    class Proficiency(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"
        EXPERT = "expert", "Expert"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="employee_skills")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="employee_skills")
    proficiency = models.CharField(max_length=20, choices=Proficiency.choices, default=Proficiency.INTERMEDIATE)
    acquired_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["employee", "skill"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "skill"], name="one_skill_entry_per_employee")
        ]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.skill.name} ({self.proficiency})"


class Certification(TimestampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="certifications")
    name = models.CharField(max_length=200)
    issuing_body = models.CharField(max_length=200, blank=True)
    credential_id = models.CharField(max_length=100, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-issue_date"]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.name}"

    @property
    def is_expired(self) -> bool:
        return self.expiry_date is not None and self.expiry_date < timezone.localdate()


class TrainingRecord(TimestampedModel):
    """Data-Dictionary.md: "training_record (I — feeds WSP/ATR)". The
    fields here (hours, cost, status, dates) are exactly what a WSP/ATR
    (SETA) submission needs (Documentation-Review-and-Gap-Analysis.md gap
    C2) — see learning/views.py::wsp_atr_export.

    REQUESTED (Sprint 15/ESS) is the server-forced starting status for a
    self-submitted enrollment request — learning/serializers.py::
    TrainingRecordSerializer.validate() strips status/hours/cost/
    completion_date from a self-submission and won't let the requester
    change them afterwards either; only a manager/hr_admin moves a record
    past REQUESTED (see PLANNED and onward)."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="training_records")
    title = models.CharField(max_length=200)
    provider = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    start_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.title} ({self.get_status_display()})"
