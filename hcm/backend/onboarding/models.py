"""Onboarding / offboarding checklist templates and instances (C1 part 3
slice 3). Spec:
docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md

Mirrors performance.AgreementTemplate's versioned-template shape
structurally (a versioned template -> an instance snapshotted from it ->
per-item state) but deliberately without its signing/scoring machinery
(spec section 2.3) -- a checklist item is ticked off, not rated or signed.
One app, one model pair, a `direction` field distinguishing onboarding from
offboarding rather than two parallel model families (spec section 2.1)."""
from __future__ import annotations

from django.db import models
from django.db.models import Q

from core_hr.base import TimestampedModel
from core_hr.models import Employee, EmploymentChange


class ChecklistTemplate(TimestampedModel):
    class Direction(models.TextChoices):
        ONBOARDING = "onboarding", "Onboarding"
        OFFBOARDING = "offboarding", "Offboarding"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    name = models.CharField(max_length=200)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    # Auto-assigned server-side (services.create_template) -- never
    # client-writable, same discipline as EmploymentChange's computed
    # fields. See spec section 4.1.
    version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklist_templates_created"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["direction", "name", "-version"]
        constraints = [
            # Includes `direction`, unlike AgreementTemplate's equivalent
            # constraint -- that model has no direction-like field, but here
            # two different directions legitimately share a name+version
            # (e.g. both seeded as "Standard onboarding"/"Standard
            # offboarding" v1), and version is auto-assigned per
            # name+direction (services.create_template), not per name alone.
            models.UniqueConstraint(
                fields=["name", "direction", "version"], name="unique_checklist_template_name_direction_version"
            )
        ]

    def __str__(self):
        return f"{self.name} v{self.version} ({self.get_direction_display()}, {self.get_status_display()})"

    @classmethod
    def current_for(cls, direction: str) -> "ChecklistTemplate | None":
        """The template an automatic hire/exit trigger (spec section 6) or a
        manual create (spec section 2.5) resolves against: the newest
        published version for this direction. None if nothing is published
        yet -- callers must treat that as "nothing to do", not an error."""
        return cls.objects.filter(direction=direction, status=cls.Status.PUBLISHED).order_by("-version").first()


class ChecklistTemplateItem(TimestampedModel):
    class OwnerRole(models.TextChoices):
        HR = "hr", "HR"
        IT = "it", "IT"
        LINE_MANAGER = "line_manager", "Line manager"
        EMPLOYEE = "employee", "Employee"
        OTHER = "other", "Other"

    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="items")
    label = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    # Who normally does this AND, for line_manager specifically, the
    # completion gate itself (spec section 3, decision 1) -- reusing the hint
    # rather than adding a second field for the same idea.
    owner_role = models.CharField(max_length=20, choices=OwnerRole.choices, default=OwnerRole.HR)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["template", "order", "id"]

    def __str__(self):
        return self.label


class ChecklistInstance(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="checklists")
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT, related_name="instances")
    # Snapshot of template.version/direction at creation -- readable even if
    # the FK is later inspected out of context, and stable if the template
    # (an unrelated later version) changes direction is never possible, but
    # keeps this row self-describing without a join.
    template_version = models.PositiveSmallIntegerField()
    direction = models.CharField(max_length=20, choices=ChecklistTemplate.Direction.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    # Set only for an offboarding instance created by the automatic exit
    # hook (spec section 6.2); null for onboarding instances and for any
    # manually-created instance.
    triggering_change = models.ForeignKey(
        EmploymentChange, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklist_instances"
    )
    # Null = created by the automatic hire/exit hook; set = the hr_admin who
    # manually triggered it (spec section 2.5).
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklists_created"
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "direction"],
                condition=Q(status="active"),
                name="one_active_checklist_per_employee_per_direction",
            )
        ]

    def __str__(self):
        return f"{self.employee.employee_number} — {self.get_direction_display()} ({self.get_status_display()})"


class ChecklistInstanceItem(TimestampedModel):
    instance = models.ForeignKey(ChecklistInstance, on_delete=models.CASCADE, related_name="items")
    # Copied from the template item at creation (spec section 2.4) -- this
    # row's identity IS the snapshot, so these are never re-synced from the
    # template after the fact.
    label = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    owner_role = models.CharField(max_length=20, choices=ChecklistTemplateItem.OwnerRole.choices)
    order = models.PositiveSmallIntegerField(default=0)
    completed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="checklist_items_completed"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["instance", "order", "id"]

    def __str__(self):
        return self.label

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
