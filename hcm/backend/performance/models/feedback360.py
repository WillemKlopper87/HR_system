"""360-degree feedback (C6, NEXT_AGENT_BRIEF.md §7.3 #20).

Structured, multi-rater input on one `PerformanceAgreement` -- distinct from
the legacy free-text `performance.Feedback` (models/cycles.py), which stays
untouched and open-authorship (right for a private note; wrong for rated
input that a Head reads alongside a KPI scorecard -- design spec §2.7).

Three models, mirroring `InterviewSession`/`InterviewScorecard`'s own split
(recruitment/models.py): `Feedback360Request` is the round (who's invited),
`Feedback360Rater` is one rater's slot (nomination + approval state),
`Feedback360Response` is what they actually submitted. "Has this rater
submitted" is derived from whether a `Feedback360Response` exists for their
slot, not stored -- this codebase's derive-don't-store philosophy.

Visibility (self/manager attributed, peer/direct_report aggregated-only-once
≥3-responses-and-never-with-free-text to the subject; full detail always to
Head/hr_admin/auditor) is enforced in the serializer's `to_representation`,
same split `InterviewScorecardSerializer`'s blind review already uses --
these models carry no visibility state, only the data. See design spec
§2.10 for the full reasoning.
"""
from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core_hr.base import TimestampedModel
from core_hr.models import Employee

from .agreements import RATING_MAX, RATING_MIN, PerformanceAgreement

FEEDBACK_360_RATING_CHOICES = [(i, str(i)) for i in range(RATING_MIN, RATING_MAX + 1)]

# Smallest N a subject genuinely cannot back-solve a single peer/direct-report
# rater's answer from (at n=2, one known or inferable value fully recovers
# the other) -- deliberately NOT views_agreements.SMALL_CELL_THRESHOLD (=5),
# which protects a demographic cell inside an org-wide aggregate, a
# different risk shape/scale from a 360 round's realistic 2-6-person rater
# pool per relationship type (design spec §2.10).
FEEDBACK_360_MIN_RESPONSES_FOR_AGGREGATE = 3


class Feedback360Request(TimestampedModel):
    """One 360 round tied to one employee's agreement. Creation is gated
    (services/feedback360.py) to `agreement.status in
    PerformanceAgreement.CONTRACTED_STATUSES` -- KPIs must already be agreed
    before "how do you work with this person" input is meaningful."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    agreement = models.ForeignKey(PerformanceAgreement, on_delete=models.CASCADE, related_name="feedback_requests")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    opened_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedback_requests_opened"
    )
    due_date = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"360 feedback for {self.agreement} ({self.get_status_display()})"


class Feedback360Rater(TimestampedModel):
    """One rater's slot within a round. `relationship` is derived
    server-side from the org chart at nomination time (same reasoning as
    performance/services/cycles.py::classify_feedback_type), never trusted
    from client input. `self`/`manager` slots are created automatically and
    pre-approved when the request opens; `peer`/`direct_report` slots start
    pending and need Head/hr_admin approval (spec §2.9)."""

    class Relationship(models.TextChoices):
        SELF = "self", "Self"
        MANAGER = "manager", "Manager / Head"
        PEER = "peer", "Peer"
        DIRECT_REPORT = "direct_report", "Direct report"

    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Pending approval"
        APPROVED = "approved", "Approved — invited"
        DECLINED_NOMINATION = "declined_nomination", "Nomination declined"
        WITHDRAWN = "withdrawn", "Withdrawn"

    request = models.ForeignKey(Feedback360Request, on_delete=models.CASCADE, related_name="raters")
    rater = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="feedback_360_rater_assignments")
    relationship = models.CharField(max_length=20, choices=Relationship.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_APPROVAL)
    nominated_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedback_360_raters_nominated"
    )
    approved_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="feedback_360_raters_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["request", "id"]
        constraints = [
            models.UniqueConstraint(fields=["request", "rater"], name="one_rater_slot_per_request")
        ]

    def __str__(self):
        return f"{self.rater.employee_number} ({self.get_relationship_display()}) on {self.request}"

    @property
    def has_submitted(self) -> bool:
        return hasattr(self, "response")


class Feedback360Response(TimestampedModel):
    """The rater's structured input -- fixed 3-criterion 1-5 vocabulary
    (matching recruitment.InterviewScorecard's precedent) plus two free-text
    fields. Only the named rater may create/edit it (force-set server-side,
    no proxy-entry), and only while the slot is approved and the request is
    open (services/feedback360.py)."""

    rater_slot = models.OneToOneField(Feedback360Rater, on_delete=models.CASCADE, related_name="response")
    collaboration_rating = models.PositiveSmallIntegerField(
        choices=FEEDBACK_360_RATING_CHOICES, validators=[MinValueValidator(RATING_MIN), MaxValueValidator(RATING_MAX)]
    )
    communication_rating = models.PositiveSmallIntegerField(
        choices=FEEDBACK_360_RATING_CHOICES, validators=[MinValueValidator(RATING_MIN), MaxValueValidator(RATING_MAX)]
    )
    reliability_rating = models.PositiveSmallIntegerField(
        choices=FEEDBACK_360_RATING_CHOICES, validators=[MinValueValidator(RATING_MIN), MaxValueValidator(RATING_MAX)]
    )
    strengths = models.TextField(blank=True)
    development_areas = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"360 response by {self.rater_slot.rater.employee_number} on {self.rater_slot.request}"
