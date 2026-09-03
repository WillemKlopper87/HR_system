"""rbac_audit.subject_export registry entry for this app's personal data
(HCM remediation H-3) -- registered from LearningConfig.ready()."""
from __future__ import annotations

from rbac_audit.subject_export import DomainExportResult, DomainStatus


def export_handler(employee) -> DomainExportResult:
    records = list(employee.training_records.order_by("created_at"))
    if not records:
        return DomainExportResult(status=DomainStatus.NO_RECORDS)
    payload = [
        {
            "title": r.title,
            "provider": r.provider,
            "status": r.status,
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "completion_date": r.completion_date.isoformat() if r.completion_date else None,
            "hours": str(r.hours) if r.hours is not None else None,
            "cost": str(r.cost) if r.cost is not None else None,
        }
        for r in records
    ]
    return DomainExportResult(status=DomainStatus.INCLUDED, record_count=len(payload), payload=payload)
