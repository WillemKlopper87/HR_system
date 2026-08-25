"""360-degree feedback workflow (C6, design spec 2026-08-25-performance-
calibration-360-design.md). `classify_relationship` is the server-side org-
chart derivation `Feedback360Rater.relationship` always uses -- never client
input -- mirroring performance/services/cycles.py::classify_feedback_type.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rbac_audit.permissions import is_in_reporting_chain

from core_hr.models import Employee
from notifications.services import notify

from ..models import PerformanceAgreement
from ..models.feedback360 import (
    FEEDBACK_360_MIN_RESPONSES_FOR_AGGREGATE,
    Feedback360Rater,
    Feedback360Request,
    Feedback360Response,
)
from .agreements import AgreementWorkflowError


def classify_relationship(candidate: Employee, agreement: PerformanceAgreement) -> str:
    """self / manager / peer / direct_report, derived from the org chart as
    at today (spec §2.9) -- never trusted from client input."""
    employee = agreement.employee
    if candidate.pk == employee.pk:
        return Feedback360Rater.Relationship.SELF
    if is_in_reporting_chain(candidate, employee):
        return Feedback360Rater.Relationship.MANAGER
    if is_in_reporting_chain(employee, candidate):
        return Feedback360Rater.Relationship.DIRECT_REPORT
    return Feedback360Rater.Relationship.PEER


@transaction.atomic
def open_request(agreement: PerformanceAgreement, *, actor: Employee, due_date=None) -> Feedback360Request:
    if agreement.status not in PerformanceAgreement.CONTRACTED_STATUSES:
        raise AgreementWorkflowError(
            "A 360 round can only be opened once the agreement's KPIs are contracted (AGREED or later)."
        )
    request = Feedback360Request.objects.create(agreement=agreement, opened_by=actor, due_date=due_date)
    # self and manager are automatic, pre-approved -- no nomination needed
    # (spec §2.9).
    Feedback360Rater.objects.create(
        request=request, rater=agreement.employee, relationship=Feedback360Rater.Relationship.SELF,
        status=Feedback360Rater.Status.APPROVED, nominated_by=actor, approved_by=actor, approved_at=timezone.now(),
    )
    if agreement.head_id:
        Feedback360Rater.objects.create(
            request=request, rater=agreement.head, relationship=Feedback360Rater.Relationship.MANAGER,
            status=Feedback360Rater.Status.APPROVED, nominated_by=actor, approved_by=actor,
            approved_at=timezone.now(),
        )
    return request


def close_request(request: Feedback360Request, *, actor: Employee) -> Feedback360Request:
    if request.status != Feedback360Request.Status.OPEN:
        raise AgreementWorkflowError("This 360 round is already closed.", conflict=True)
    request.status = Feedback360Request.Status.CLOSED
    request.closed_at = timezone.now()
    request.save(update_fields=["status", "closed_at"])
    return request


@transaction.atomic
def nominate_rater(request: Feedback360Request, candidate: Employee, *, actor: Employee) -> Feedback360Rater:
    if request.status != Feedback360Request.Status.OPEN:
        raise AgreementWorkflowError("This 360 round is closed to new nominations.", conflict=True)
    if Feedback360Rater.objects.filter(request=request, rater=candidate).exists():
        raise AgreementWorkflowError("That person already has a rater slot on this round.", conflict=True)
    relationship = classify_relationship(candidate, request.agreement)
    if relationship in (Feedback360Rater.Relationship.SELF, Feedback360Rater.Relationship.MANAGER):
        raise AgreementWorkflowError(
            "This person is already an automatic rater (self or manager) — no nomination needed."
        )
    return Feedback360Rater.objects.create(
        request=request, rater=candidate, relationship=relationship,
        status=Feedback360Rater.Status.PENDING_APPROVAL, nominated_by=actor,
    )


def approve_rater(rater_slot: Feedback360Rater, *, actor: Employee) -> Feedback360Rater:
    if rater_slot.status != Feedback360Rater.Status.PENDING_APPROVAL:
        raise AgreementWorkflowError("Only a pending nomination can be approved.", conflict=True)
    rater_slot.status = Feedback360Rater.Status.APPROVED
    rater_slot.approved_by = actor
    rater_slot.approved_at = timezone.now()
    rater_slot.save(update_fields=["status", "approved_by", "approved_at"])
    notify(
        recipient=rater_slot.rater, kind="review_launch",
        title="You've been asked for 360° feedback",
        body=f"For {rater_slot.request.agreement.employee.first_name} {rater_slot.request.agreement.employee.last_name}.",
        link="/my-feedback-requests",
    )
    return rater_slot


def decline_rater(rater_slot: Feedback360Rater, *, actor: Employee) -> Feedback360Rater:
    if rater_slot.status != Feedback360Rater.Status.PENDING_APPROVAL:
        raise AgreementWorkflowError("Only a pending nomination can be declined.", conflict=True)
    rater_slot.status = Feedback360Rater.Status.DECLINED_NOMINATION
    rater_slot.save(update_fields=["status"])
    return rater_slot


def withdraw_rater(rater_slot: Feedback360Rater, *, actor: Employee) -> Feedback360Rater:
    """The rater themself opts out (or hr_admin/Head removes them) before
    responding -- once a response exists, it stands (matches EvidenceItem's
    "no hard delete post sign-off" posture for anything already recorded)."""
    if rater_slot.has_submitted:
        raise AgreementWorkflowError("This rater has already submitted a response and cannot be withdrawn.")
    rater_slot.status = Feedback360Rater.Status.WITHDRAWN
    rater_slot.save(update_fields=["status"])
    return rater_slot


@transaction.atomic
def submit_response(
    rater_slot: Feedback360Rater, *, actor: Employee, collaboration_rating: int, communication_rating: int,
    reliability_rating: int, strengths: str = "", development_areas: str = "",
) -> Feedback360Response:
    if actor.pk != rater_slot.rater_id:
        raise AgreementWorkflowError("Only the named rater can submit this response.")
    if rater_slot.status != Feedback360Rater.Status.APPROVED:
        raise AgreementWorkflowError("This rater slot is not approved to respond.")
    if rater_slot.request.status != Feedback360Request.Status.OPEN:
        raise AgreementWorkflowError("This 360 round is closed.", conflict=True)
    response, _ = Feedback360Response.objects.update_or_create(
        rater_slot=rater_slot,
        defaults={
            "collaboration_rating": collaboration_rating, "communication_rating": communication_rating,
            "reliability_rating": reliability_rating, "strengths": strengths, "development_areas": development_areas,
        },
    )
    return response


def aggregate_for(request: Feedback360Request, relationship: str) -> dict | None:
    """Pooled ratings-only average for one relationship bucket, gated on the
    ≥3-response floor (spec §2.10). Returns None below the floor -- the
    caller renders "not enough responses yet" rather than a number, and never
    exposes free text here regardless of count."""
    responses = Feedback360Response.objects.filter(
        rater_slot__request=request, rater_slot__relationship=relationship
    )
    count = responses.count()
    if count < FEEDBACK_360_MIN_RESPONSES_FOR_AGGREGATE:
        return None
    totals = {"collaboration_rating": 0, "communication_rating": 0, "reliability_rating": 0}
    for response in responses:
        for field in totals:
            totals[field] += getattr(response, field)
    return {
        "response_count": count,
        **{field: round(total / count, 2) for field, total in totals.items()},
    }


__all__ = [
    "aggregate_for",
    "approve_rater",
    "classify_relationship",
    "close_request",
    "decline_rater",
    "nominate_rater",
    "open_request",
    "submit_response",
    "withdraw_rater",
]
