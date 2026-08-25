from __future__ import annotations

from django.db import models
from django.utils import timezone

from core_hr.base import TimestampedModel
from core_hr.models import Department, Employee, OccupationalLevel


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
    # C6 (docs/superpowers/specs/2026-08-25-mandatory-training-compliance-
    # design.md §2.5): nullable so ad-hoc/non-catalogue training (including
    # every pre-existing row, and the Sprint-15 self-service flow's own
    # free-text submissions) keeps working unmodified. Compliance
    # derivation (learning/compliance.py) only ever reads `course`, never
    # `title` -- a historical free-text row never retroactively satisfies
    # a CourseRequirement, by design (no reliable title->course mapping to
    # backfill safely).
    course = models.ForeignKey(
        "Course", on_delete=models.SET_NULL, null=True, blank=True, related_name="training_records"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    start_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.title} ({self.get_status_display()})"


class Course(TimestampedModel):
    """Public-tier catalogue (same reasoning as Skill's own docstring: the
    catalogue itself isn't sensitive). `mandatory` is catalogue metadata
    classifying the *kind* of course (compliance/statutory vs. an ordinary
    elective) -- distinct from CourseRequirement, which is the actual
    scoped rule; see design spec §2.2 for why both exist."""

    name = models.CharField(max_length=200, unique=True)
    provider = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    mandatory = models.BooleanField(default=False)
    # Renewal cycle in days (e.g. 365 for an annual compliance refresher);
    # None = a completion never expires once recorded. Days, not months,
    # for simple date arithmetic without a calendar-months dependency.
    validity_days = models.PositiveIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CourseRequirement(TimestampedModel):
    """'Required for role' rule (design spec §2.3): course.PROTECT mirrors
    EmployeeSkill.skill -- an active rule shouldn't be able to have its
    catalogue entry silently deleted out from under it. department/
    occupational_level are both optional; both null means an org-wide
    mandate (e.g. a POPIA-awareness induction everyone must complete).
    Compliance is derived on read (learning/compliance.py), never stored
    here or anywhere else -- same philosophy as
    establishment.Position.current_occupant."""

    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="requirements")
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, null=True, blank=True, related_name="course_requirements"
    )
    occupational_level = models.ForeignKey(
        OccupationalLevel, on_delete=models.PROTECT, null=True, blank=True, related_name="course_requirements"
    )
    effective_from = models.DateField()
    due_within_days = models.PositiveIntegerField()
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["course", "department", "occupational_level"]

    def __str__(self):
        scope = self.department.name if self.department else "Org-wide"
        if self.occupational_level:
            scope = f"{scope} / {self.occupational_level.name}"
        return f"{self.course.name} — required for {scope}"
