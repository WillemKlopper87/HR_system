"""Succession planning / talent pools (C6). Spec:
docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md

Two models: `CriticalPost` (which establishment.Position posts are
succession-critical) and `SuccessionCandidate` (who's been nominated as a
potential successor, and how ready). Both single-row-write, validated in
their serializers (spec §2.4) -- no services.py, this isn't a state
machine the way Position's approval chain or the onboarding checklists
are."""
from __future__ import annotations

from core_hr.base import TimestampedModel
from core_hr.models import Employee
from django.db import models
from django.db.models import Q
from establishment.models import Position
from simple_history.models import HistoricalRecords


class CriticalPost(TimestampedModel):
    """One row per Position ever flagged succession-critical (spec §2.3).
    `active` toggles the flag without deleting -- unflagging preserves the
    history of having been flagged and why, and a later re-flag reuses the
    same row rather than creating a second lineage for the same post."""

    position = models.OneToOneField(Position, on_delete=models.PROTECT, related_name="critical_post_flag")
    reason = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    flagged_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="critical_posts_flagged"
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["position__post_number"]

    def __str__(self):
        state = "critical" if self.active else "unflagged"
        return f"{self.position.post_number} ({state})"


class SuccessionCandidate(TimestampedModel):
    """A nomination of one employee as a potential successor for one
    CriticalPost. `active` withdraws a nomination without deleting it
    (spec §4.2) -- multiple historical rows for the same (critical_post,
    employee) pair are allowed, so a withdrawn-then-later-renominated
    candidate keeps a full trail rather than one row silently reused."""

    class Readiness(models.TextChoices):
        READY_NOW = "ready_now", "Ready now"
        READY_1_2_YEARS = "ready_1_2_years", "Ready in 1–2 years"
        READY_3_PLUS_YEARS = "ready_3_plus_years", "Ready in 3+ years"
        DEVELOPMENT_NEEDED = "development_needed", "Development needed"

    # Readiness bands counted as "ready soon" for the data-quality check
    # (spec §2.9) -- a set, not just READY_NOW, matching the brief's own
    # "no ready-now or ready-soon successor" wording.
    READY_SOON = (Readiness.READY_NOW, Readiness.READY_1_2_YEARS)

    critical_post = models.ForeignKey(CriticalPost, on_delete=models.CASCADE, related_name="candidates")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="succession_nominations")
    readiness = models.CharField(max_length=20, choices=Readiness.choices)
    notes = models.TextField(blank=True)
    nominated_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="succession_candidates_nominated"
    )
    active = models.BooleanField(default=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["critical_post", "employee"]
        constraints = [
            models.UniqueConstraint(
                fields=["critical_post", "employee"],
                condition=Q(active=True),
                name="one_active_nomination_per_post_per_employee",
            )
        ]

    def __str__(self):
        return f"{self.employee.employee_number} — {self.critical_post.position.post_number} ({self.get_readiness_display()})"
