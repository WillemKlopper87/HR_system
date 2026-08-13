from __future__ import annotations

import json

from django.db import transaction
from django.utils import timezone
from rbac_audit.models import ConsentRecord

from . import webhooks
from .adapters.registry import get_active_adapter
from .models import AssessmentAssignment, AssessmentResult


class ConsentRequiredError(ValueError):
    pass


class WebhookProcessingError(ValueError):
    pass


def _has_assessment_consent(*, employee=None, applicant_id=None) -> bool:
    qs = ConsentRecord.objects.filter(purpose=ConsentRecord.Purpose.ASSESSMENT, withdrawn_at__isnull=True)
    if employee is not None:
        return qs.filter(employee=employee).exists()
    return qs.filter(applicant_id=applicant_id).exists()


@transaction.atomic
def assign_assessment(
    *, employee=None, applicant_id=None, assessment_type, assigned_by=None
) -> AssessmentAssignment:
    """Sprint 12 task: "Consent capture before assessment assignment" —
    enforced here, not left to the UI, same as recruitment's demographic-
    consent gate (recruitment/serializers.py::ApplicantSerializer.validate)."""
    if (employee is None) == (applicant_id is None):
        raise ValueError("Exactly one of employee or applicant_id must be provided.")
    if not _has_assessment_consent(employee=employee, applicant_id=applicant_id):
        hint = (
            "POST /api/v1/assessment-assignments/consent/ (employee subject)"
            if employee is not None
            else f"POST /api/v1/applicants/{applicant_id}/consent/ with purpose=assessment"
        )
        raise ConsentRequiredError(f"Assessment consent has not been captured for this subject — {hint} first.")

    adapter = get_active_adapter()
    assignment = AssessmentAssignment.objects.create(
        employee=employee,
        applicant_id=applicant_id,
        assessment_type=assessment_type,
        assigned_by=assigned_by,
        provider_key=adapter.provider_key,
    )
    outcome = adapter.assign(assignment)
    assignment.provider_reference = outcome.provider_reference
    assignment.access_url = outcome.access_url
    assignment.save(update_fields=["provider_reference", "access_url"])
    return assignment


@transaction.atomic
def process_webhook_result(
    *, provider_reference: str, status: str, raw_score: str = "", summary: str = "", detail: dict | None = None
) -> AssessmentAssignment:
    """Idempotent by design (webhooks.py's replay-window docstring) —
    reprocessing the same completed provider_reference updates the result
    in place rather than erroring or duplicating it, since real providers
    commonly retry webhook delivery."""
    try:
        assignment = AssessmentAssignment.objects.select_related("employee").get(provider_reference=provider_reference)
    except AssessmentAssignment.DoesNotExist as exc:
        raise WebhookProcessingError(f"No assignment found for provider_reference={provider_reference!r}") from exc

    if status not in AssessmentAssignment.Status.values:
        raise WebhookProcessingError(f"Unknown status {status!r} from provider.")

    assignment.status = status
    update_fields = ["status"]
    if status == AssessmentAssignment.Status.COMPLETED:
        assignment.completed_at = assignment.completed_at or timezone.now()
        update_fields.append("completed_at")
        AssessmentResult.objects.update_or_create(
            assignment=assignment,
            defaults={"raw_score": raw_score, "summary": summary, "detail": detail or {}},
        )
    assignment.save(update_fields=update_fields)
    return assignment


def simulate_provider_completion(assignment: AssessmentAssignment) -> AssessmentAssignment:
    """Local-dev/demo utility standing in for a real provider's async
    webhook delivery — there is no real provider under contract yet
    (Sprint-0-Decision-Log.md A4). Builds a plausible fake result, signs
    it, and routes it through webhooks.verify_signature() +
    process_webhook_result() exactly like a real inbound delivery would,
    so this exercises the real pipeline rather than bypassing it."""
    band = assignment.id % 3
    summary, raw_score = {
        0: ("Above-average overall profile; strong in analytical reasoning.", "78"),
        1: ("Average overall profile, broadly in line with the role benchmark.", "55"),
        2: ("Below-benchmark in this attempt; consider a follow-up session.", "34"),
    }[band]
    payload = {
        "provider_reference": assignment.provider_reference,
        "status": AssessmentAssignment.Status.COMPLETED,
        "raw_score": raw_score,
        "summary": summary,
        "detail": {"simulated": True, "band": band},
    }
    raw_body = json.dumps(payload).encode()
    timestamp = int(timezone.now().timestamp())
    signature = webhooks.sign_payload(raw_body, timestamp=timestamp)

    webhooks.verify_signature(raw_body, signature=signature, timestamp=str(timestamp))
    parsed = json.loads(raw_body)
    return process_webhook_result(
        provider_reference=parsed["provider_reference"],
        status=parsed["status"],
        raw_score=parsed["raw_score"],
        summary=parsed["summary"],
        detail=parsed["detail"],
    )
