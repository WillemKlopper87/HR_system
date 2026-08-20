"""Position/establishment management (C1, part 1 of 3 -- see
docs/superpowers/specs/2026-08-19-position-establishment-design.md).

A Position is an approved, individually-numbered post, independent of who
currently holds it -- persists across incumbents, matching PFMA-style
establishment control. Occupancy is always DERIVED from `core_hr.
EmployeeVersion.position` (current_occupant/is_vacant below), never stored,
so it can never drift out of sync with who's actually employed.

This app joins SHARED_KERNEL (rbac_audit/test_module_boundaries.py) because
both core_hr (EmployeeVersion.position) and recruitment (Requisition.
positions) need a direct relationship into it, not a queries.py read seam.
"""
from __future__ import annotations

from core_hr.base import TimestampedModel
from core_hr.models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel
from django.db import models
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords


class PositionQuerySet(models.QuerySet):
    def vacant(self):
        occupied_ids = EmployeeVersion.objects.filter(
            valid_to__isnull=True, position__isnull=False
        ).values_list("position_id", flat=True)
        return self.filter(status=Position.Status.APPROVED).exclude(id__in=occupied_ids)


class Position(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    post_number = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="positions")
    occupational_level = models.ForeignKey(OccupationalLevel, on_delete=models.PROTECT, related_name="positions")
    job_grade = models.ForeignKey(
        JobGrade, null=True, blank=True, on_delete=models.PROTECT, related_name="positions"
    )
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="positions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # Index into settings.POSITION_APPROVAL_CHAIN; meaningful only while
    # status == IN_REVIEW (see establishment/services.py).
    current_step = models.PositiveSmallIntegerField(default=0)
    proposed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="positions_proposed"
    )

    objects = PositionQuerySet.as_manager()
    history = HistoricalRecords()

    class Meta:
        ordering = ["post_number"]

    def __str__(self):
        return f"{self.post_number}: {self.title} ({self.get_status_display()})"

    @cached_property
    def current_occupant(self) -> EmployeeVersion | None:
        """Cached per instance: PositionSerializer reads this twice for
        every row it renders (is_vacant, then current_incumbent_number),
        and the Positions page's whole job is listing every post on the
        establishment. Each request builds its rows from a fresh queryset,
        so a cached value never outlives the request that computed it."""
        return (
            EmployeeVersion.objects.filter(valid_to__isnull=True, position=self)
            .select_related("employee")
            .first()
        )

    @property
    def is_vacant(self) -> bool:
        return self.status == self.Status.APPROVED and self.current_occupant is None


class PositionApprovalStep(TimestampedModel):
    """Append-only audit trail, one row per approval-chain decision. `role`
    is a SNAPSHOT of which role this step required (read from settings at
    decision time), not a live reference -- so a later chain change never
    rewrites history. `created_at` (from TimestampedModel) is the decision
    timestamp."""

    class Decision(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name="approval_steps")
    step_index = models.PositiveSmallIntegerField()
    role = models.CharField(max_length=40)
    actor = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decision = models.CharField(max_length=20, choices=Decision.choices)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["position", "step_index", "created_at"]

    def __str__(self):
        return f"{self.position.post_number} step {self.step_index} ({self.role}): {self.decision}"
