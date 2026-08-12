from __future__ import annotations

from .models import AuditLogEntry


def log_access(
    *, actor, action, entity_type, entity_id, field_tier, fields_touched="", request_id="", ip_address=None
) -> AuditLogEntry:
    return AuditLogEntry.objects.create(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        field_tier=field_tier,
        fields_touched=fields_touched,
        request_id=request_id,
        ip_address=ip_address,
    )
