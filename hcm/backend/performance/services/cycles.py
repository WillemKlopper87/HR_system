from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rbac_audit.permissions import is_in_reporting_chain

from core_hr.models import Employee

from ..models import Feedback, Review, ReviewCycle


@transaction.atomic
def launch_review_cycle(cycle: ReviewCycle) -> int:
    """Snapshots every currently active employee into a Review row for
    this cycle, with `manager` fixed at launch time. Idempotent — running
    it twice (e.g. a retried request) doesn't duplicate rows, thanks to
    get_or_create on the (review_cycle, employee) unique constraint."""
    if cycle.status != ReviewCycle.Status.DRAFT:
        raise ValueError("Only a draft cycle can be launched.")

    created = 0
    for employee in Employee.objects.all():
        version = employee.current_version
        if version is None:
            continue
        _, was_created = Review.objects.get_or_create(
            review_cycle=cycle, employee=employee, defaults={"manager": version.manager}
        )
        if was_created:
            created += 1

    cycle.status = ReviewCycle.Status.LAUNCHED
    cycle.launched_at = timezone.now()
    cycle.save(update_fields=["status", "launched_at"])
    return created


def close_review_cycle(cycle: ReviewCycle) -> ReviewCycle:
    if cycle.status != ReviewCycle.Status.LAUNCHED:
        raise ValueError("Only a launched cycle can be closed.")
    cycle.status = ReviewCycle.Status.CLOSED
    cycle.closed_at = timezone.now()
    cycle.save(update_fields=["status", "closed_at"])
    return cycle


def classify_feedback_type(author: Employee | None, employee: Employee) -> str:
    """Manager feedback if the author is anywhere in the employee's
    reporting chain, peer feedback otherwise — computed from the org
    chart, not trusted from client input."""
    if author is not None and is_in_reporting_chain(author, employee):
        return Feedback.FeedbackType.MANAGER
    return Feedback.FeedbackType.PEER
