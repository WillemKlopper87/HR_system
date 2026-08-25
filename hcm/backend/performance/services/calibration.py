"""Calibration / moderation workflow (C6, design spec 2026-08-25-performance-
calibration-360-design.md). Deliberately small: hr_admin opens a session,
records one outcome per agreement in the cohort (unchanged or adjusted, both
reasoned), then closes it. See the spec §2.3-§2.4 for why this is not a live
multi-party workflow and why an adjustment never triggers re-signature.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core_hr.models import Employee
from notifications.services import notify
from rbac_audit.audit import log_access
from rbac_audit.models import AuditLogEntry
from rbac_audit.tiers import FieldTier

from ..models import PerformanceAgreement
from ..models.calibration import CalibrationAdjustment, CalibrationSession
from .agreements import AgreementWorkflowError

CALIBRATION_ELIGIBLE_STATUSES = (PerformanceAgreement.Status.FINAL_SIGNED, PerformanceAgreement.Status.ARCHIVED)


def eligible_agreements(session: CalibrationSession):
    """The cohort a session covers: this period, this department (or every
    department if blank), only agreements whose final score is actually
    frozen (spec §2.5)."""
    # `current_version` is a computed property (core_hr.models.Employee),
    # not a real relation -- can't select_related through it; the dashboards
    # this reuses the grouping unit from (rating_distribution/completion in
    # views_agreements.py) accept the same one-query-per-employee cost at
    # this scale.
    qs = PerformanceAgreement.objects.filter(
        period=session.period, status__in=CALIBRATION_ELIGIBLE_STATUSES
    ).select_related("employee", "head")
    if session.department_id is None:
        return qs
    return [
        agreement
        for agreement in qs
        if agreement.employee.current_version is not None
        and agreement.employee.current_version.department_id == session.department_id
    ]


@transaction.atomic
def open_session(
    *, period, department=None, actor: Employee, meeting_date=None, participants_note: str = ""
) -> CalibrationSession:
    session = CalibrationSession.objects.create(
        period=period, department=department, convened_by=actor,
        meeting_date=meeting_date, participants_note=participants_note or "",
    )
    log_access(
        actor=actor, action=AuditLogEntry.Action.CREATE, entity_type="performance.CalibrationSession",
        entity_id=session.pk, field_tier=FieldTier.SENSITIVE,
        fields_touched=f"calibration session opened for {period.name} / {department or 'org-wide'}",
    )
    return session


@transaction.atomic
def record_calibration_outcome(
    session: CalibrationSession, agreement: PerformanceAgreement, *, actor: Employee, reason: str,
    new_score=None,
) -> CalibrationAdjustment:
    """Record one agreement's outcome. `new_score=None` means "reviewed, no
    change needed" -- still requires a reason, still a real audit row (spec
    §2.4). Never touches signatures/documents; only `final_score`/
    `hr_attention`* move, and `PerformanceAgreement.history` (existing
    simple_history) captures that change automatically."""
    if session.status != CalibrationSession.Status.OPEN:
        raise AgreementWorkflowError("This calibration session is already completed.", conflict=True)
    if agreement.status not in CALIBRATION_ELIGIBLE_STATUSES:
        raise AgreementWorkflowError(
            "Only a fully final-signed (or archived) agreement can be calibrated."
        )
    if not (reason or "").strip():
        raise AgreementWorkflowError("A reason is required for every calibration outcome, even 'no change'.")
    if CalibrationAdjustment.objects.filter(session=session, agreement=agreement).exists():
        raise AgreementWorkflowError(
            "This agreement already has a recorded outcome in this session.", conflict=True
        )

    previous = agreement.final_score
    adjustment = CalibrationAdjustment.objects.create(
        session=session, agreement=agreement, previous_score=previous, new_score=new_score,
        reason=reason.strip(), adjusted_by=actor,
    )

    if new_score is not None and new_score != previous:
        agreement.final_score = new_score
        threshold = agreement.period.attention_threshold
        if new_score < threshold:
            agreement.hr_attention = True
            agreement.hr_attention_reason = f"calibration-adjusted score {new_score} is below {threshold}"[:300]
        agreement.save(update_fields=["final_score", "hr_attention", "hr_attention_reason"])
        log_access(
            actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type="performance.PerformanceAgreement",
            entity_id=agreement.pk, field_tier=FieldTier.SENSITIVE,
            fields_touched=(
                f"final_score adjusted by calibration session {session.pk}: "
                f"{previous} → {new_score} ({reason.strip()[:150]})"
            ),
        )
        notify(
            recipient=agreement.employee, kind="ee_signoff",
            title=f"Your {agreement.period.name} final score was adjusted",
            body=f"Following departmental calibration: {reason.strip()}",
            link="/my-performance",
        )
        if agreement.head_id:
            notify(
                recipient=agreement.head, kind="ee_signoff",
                title=f"{agreement.employee.first_name} {agreement.employee.last_name}'s score was calibrated",
                body=f"{previous} → {new_score}: {reason.strip()}",
                link="/team-performance",
            )
    return adjustment


def close_session(session: CalibrationSession, *, actor: Employee) -> CalibrationSession:
    if session.status != CalibrationSession.Status.OPEN:
        raise AgreementWorkflowError("This session is already completed.", conflict=True)
    session.status = CalibrationSession.Status.COMPLETED
    session.completed_at = timezone.now()
    session.save(update_fields=["status", "completed_at"])
    log_access(
        actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type="performance.CalibrationSession",
        entity_id=session.pk, field_tier=FieldTier.SENSITIVE,
        fields_touched=f"calibration session closed ({session.adjustments.count()} outcome(s) recorded)",
    )
    return session


__all__ = [
    "CALIBRATION_ELIGIBLE_STATUSES",
    "close_session",
    "eligible_agreements",
    "open_session",
    "record_calibration_outcome",
]
