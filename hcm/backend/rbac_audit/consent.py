from __future__ import annotations

from django.utils import timezone

from .audit import log_access
from .models import AuditLogEntry, ConsentRecord
from .tiers import FieldTier


def record_consent(*, employee, purpose, lawful_basis, text_version, actor=None) -> ConsentRecord:
    """Capture a consent decision (POPIA — Data-Dictionary.md
    consent_record). Sprint 15's self-service UI will be the primary
    caller once built; HR-assisted capture can call this directly."""
    consent = ConsentRecord.objects.create(
        employee=employee,
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


def has_active_consent(employee, purpose: str) -> bool:
    return ConsentRecord.objects.filter(
        employee=employee, purpose=purpose, withdrawn_at__isnull=True
    ).exists()
