from __future__ import annotations

from django.utils import timezone

from .audit import log_access
from .models import AuditLogEntry, ConsentRecord
from .tiers import FieldTier


def record_consent(
    *, employee=None, applicant=None, purpose, lawful_basis, text_version, actor=None
) -> ConsentRecord:
    """Capture a consent decision for exactly one subject — an employee
    (Sprint 15's self-service UI will be its primary caller) or an
    applicant (recruitment's demographic capture, Sprint 4). Pass `actor`
    explicitly when the subject isn't who's operating the request, e.g. a
    recruiter capturing consent on an applicant's behalf — applicants
    aren't core_hr.Employee records and can't be an AuditLogEntry actor."""
    if (employee is None) == (applicant is None):
        raise ValueError("Exactly one of employee or applicant must be provided")
    consent = ConsentRecord.objects.create(
        employee=employee,
        applicant=applicant,
        purpose=purpose,
        lawful_basis=lawful_basis,
        granted_at=timezone.now(),
        text_version=text_version,
    )
    log_access(
        actor=actor or employee,
        action=AuditLogEntry.Action.CREATE,
        entity_type="rbac_audit.ConsentRecord",
        entity_id=consent.pk,
        field_tier=FieldTier.SENSITIVE,
        fields_touched=purpose,
    )
    return consent


def withdraw_consent(consent: ConsentRecord, *, actor=None) -> ConsentRecord:
    if consent.withdrawn_at is not None:
        raise ValueError("Consent has already been withdrawn")
    consent.withdrawn_at = timezone.now()
    consent.save(update_fields=["withdrawn_at"])
    log_access(
        actor=actor or consent.employee,
        action=AuditLogEntry.Action.UPDATE,
        entity_type="rbac_audit.ConsentRecord",
        entity_id=consent.pk,
        field_tier=FieldTier.SENSITIVE,
        fields_touched="withdrawn_at",
    )
    return consent


def has_active_consent(*, employee=None, applicant=None, purpose: str) -> bool:
    if (employee is None) == (applicant is None):
        raise ValueError("Exactly one of employee or applicant must be provided")
    queryset = ConsentRecord.objects.filter(purpose=purpose, withdrawn_at__isnull=True)
    queryset = queryset.filter(employee=employee) if employee is not None else queryset.filter(applicant=applicant)
    return queryset.exists()
