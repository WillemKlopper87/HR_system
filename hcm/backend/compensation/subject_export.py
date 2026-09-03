"""rbac_audit.subject_export registry entry for this app's personal data
(HCM remediation H-3) -- registered from CompensationConfig.ready()."""
from __future__ import annotations

from rbac_audit.subject_export import DomainExportResult, DomainStatus


def export_handler(employee) -> DomainExportResult:
    proposals = list(employee.comp_proposals.order_by("created_at"))
    if not proposals:
        return DomainExportResult(status=DomainStatus.NO_RECORDS)
    payload = [
        {
            "proposal_type": p.proposal_type,
            "status": p.status,
            "proposed_annual_salary": str(p.proposed_annual_salary) if p.proposed_annual_salary is not None else None,
            "bonus_amount": str(p.bonus_amount) if p.bonus_amount is not None else None,
            "justification": p.justification,
            "created_at": p.created_at.isoformat(),
        }
        for p in proposals
    ]
    return DomainExportResult(status=DomainStatus.INCLUDED, record_count=len(payload), payload=payload)
