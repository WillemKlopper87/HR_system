from __future__ import annotations

from django.db import models

from core_hr.base import TimestampedModel
from core_hr.models import Employee


class ReviewCycle(TimestampedModel):
    class CycleType(models.TextChoices):
        ANNUAL = "annual", "Annual"
        BIANNUAL = "biannual", "Biannual"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        LAUNCHED = "launched", "Launched"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=200)
    cycle_type = models.CharField(max_length=20, choices=CycleType.choices, default=CycleType.ANNUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField()
    end_date = models.DateField()
    launched_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="review_cycles_created"
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class Goal(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="goals")
    manager = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="goals_assigned"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="goals_created"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.title}"


class Review(TimestampedModel):
    """One row per employee per cycle, created in bulk when the cycle is
    launched (performance/services.py::launch_review_cycle) — `manager` is
    snapshotted at that point so a mid-cycle org change doesn't silently
    reassign who's reviewing whom.

    Deliberately not a TieredModelSerializer-gated model even though
    ratings/comments are Sensitive-tier: RBAC-Roles.md says line_manager
    "sees own team's reviews/goals" individually, but line_manager's
    generic Sensitive-tier grant is closed (aggregate-only, for
    demographics). Object-level row-scope (RowScopePermission) is the
    real gate here, same as recruitment's offer-pay exception."""

    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    review_cycle = models.ForeignKey(ReviewCycle, on_delete=models.CASCADE, related_name="reviews")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="reviews")
    manager = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews_to_complete"
    )

    self_rating = models.PositiveSmallIntegerField(null=True, blank=True, choices=RATING_CHOICES)
    self_comments = models.TextField(blank=True)
    self_submitted_at = models.DateTimeField(null=True, blank=True)

    manager_rating = models.PositiveSmallIntegerField(null=True, blank=True, choices=RATING_CHOICES)
    manager_comments = models.TextField(blank=True)
    manager_submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["review_cycle", "employee"]
        constraints = [
            models.UniqueConstraint(fields=["review_cycle", "employee"], name="one_review_per_employee_per_cycle")
        ]

    def __str__(self):
        return f"{self.employee.employee_number} — {self.review_cycle.name}"

    @property
    def completion_status(self) -> str:
        if self.self_submitted_at and self.manager_submitted_at:
            return "completed"
        if self.manager_submitted_at:
            return "manager_submitted"
        if self.self_submitted_at:
            return "self_submitted"
        return "not_started"


class Feedback(TimestampedModel):
    """feedback_type is derived server-side from the org chart at creation
    time (is the author in the employee's reporting chain?), not trusted
    from client input — see performance/services.py::classify_feedback_type.
    Creation is open to any authenticated employee (peer feedback crosses
    the org chart by definition); reading is row-scoped to the subject."""

    class FeedbackType(models.TextChoices):
        MANAGER = "manager", "Manager feedback"
        PEER = "peer", "Peer feedback"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="feedback_received")
    author = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedback_given"
    )
    feedback_type = models.CharField(max_length=20, choices=FeedbackType.choices)
    text = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_feedback_type_display()} for {self.employee.employee_number}"
