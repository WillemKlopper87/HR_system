"""Performance-agreement workflow (PC-1, ADR-010).

The state machine lives here, not in views, so every route into it (API,
management command, future import) obeys the same rules:

    draft ──submit(employee)──▶ submitted ──return(head)──▶ returned ──submit──▶ …
                                    └─approve(head)─▶ approved
    approved ──sign(employee)──▶ employee_signed ──sign(head|delegate)──▶ agreed

Hard rules (user-confirmed, KPI-Contracting-Investigation.md §2a):
* weights must sum to exactly 1.00 before submission, every element needs all
  five level descriptors;
* the employee signs first, then the Head — the Head's signature is refused
  (409 at the API) until the employee's exists for that stage+revision;
* the Head may be substituted only by an active `SigningDelegation`, and the
  signature then records `acting_for`;
* signing is against a *generated PDF snapshot*: its sha256 is stored on the
  signature, so "what was signed" is provable later;
* HR is a recipient, never a signatory.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import authenticate
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from core_hr.models import Employee
from rbac_audit.audit import log_access
from rbac_audit.models import AuditLogEntry
from rbac_audit.stepup import has_active_step_up_grant
from rbac_audit.tiers import FieldTier

from ..models import (
    AgreementDocument,
    AgreementElement,
    AgreementSignature,
    AgreementTemplate,
    PDPItem,
    PerformanceAgreement,
    PerformancePeriod,
    PeriodPhase,
    SigningDelegation,
)
from ..pdf import render_agreement_pdf

WEIGHT_TOLERANCE = Decimal("0.0005")
REQUIRED_LEVELS = {"1", "2", "3", "4", "5"}


class AgreementWorkflowError(ValueError):
    """A state-machine or validation rule was broken. Views map this to 400/409."""

    def __init__(self, message: str, *, conflict: bool = False):
        super().__init__(message)
        self.conflict = conflict


# --- periods & templates ----------------------------------------------------


def clone_period(previous: PerformancePeriod, *, name: str, actor=None) -> PerformancePeriod:
    """Next financial year from the last one: dates +1 year, same phase
    windows and reminder offsets. The FY runs 1 Apr → 31 Mar (user-confirmed)."""
    if PerformancePeriod.objects.filter(name=name).exists():
        raise AgreementWorkflowError(f"A period named {name} already exists.")

    def plus_year(d: date) -> date:
        try:
            return d.replace(year=d.year + 1)
        except ValueError:  # 29 Feb
            return d.replace(year=d.year + 1, day=28)

    with transaction.atomic():
        period = PerformancePeriod.objects.create(
            name=name,
            start_date=plus_year(previous.start_date),
            end_date=plus_year(previous.end_date),
            created_by=actor,
            attention_threshold=previous.attention_threshold,
        )
        for phase in previous.phases.all():
            PeriodPhase.objects.create(
                period=period,
                stage=phase.stage,
                opens_on=plus_year(phase.opens_on),
                due_on=plus_year(phase.due_on),
                reminder_offsets_days=list(phase.reminder_offsets_days),
                overdue_every_days=phase.overdue_every_days,
            )
    return period


def publish_template(template: AgreementTemplate, *, actor=None) -> AgreementTemplate:
    if template.status != AgreementTemplate.Status.DRAFT:
        raise AgreementWorkflowError("Only a draft template can be published.")
    if not template.elements.exists():
        raise AgreementWorkflowError("A template needs at least one KPI before it can be published.")
    total = sum((e.default_weight for e in template.elements.all()), Decimal("0"))
    if abs(total - Decimal("1")) > WEIGHT_TOLERANCE:
        raise AgreementWorkflowError(f"Template default weights must sum to 1.00 (currently {total}).")
    for element in template.elements.all():
        missing = REQUIRED_LEVELS - set(map(str, element.level_descriptors or {}))
        if missing:
            raise AgreementWorkflowError(
                f'"{element.kpi_title}" is missing target descriptors for level(s) {", ".join(sorted(missing))}.'
            )
    template.status = AgreementTemplate.Status.PUBLISHED
    template.published_at = timezone.now()
    template.save(update_fields=["status", "published_at"])
    return template


def pick_template(period: PerformancePeriod, employee: Employee) -> AgreementTemplate | None:
    """Most specific published template that applies: pinned to this period
    first, then unpinned; newest version wins within each."""
    candidates = AgreementTemplate.objects.filter(status=AgreementTemplate.Status.PUBLISHED).order_by(
        "-period_id", "-version"
    )
    for template in candidates.filter(period=period):
        if template.applies_to(employee):
            return template
    for template in candidates.filter(period__isnull=True):
        if template.applies_to(employee):
            return template
    return None


# --- agreements -------------------------------------------------------------


@transaction.atomic
def create_agreement(
    *, period: PerformancePeriod, employee: Employee, template: AgreementTemplate | None = None, actor=None
) -> PerformanceAgreement:
    """Instantiate one employee's scorecard from a template. The Head is
    snapshotted from the org chart now (same reasoning as Review.manager):
    a later reporting change must not silently move who signs."""
    if PerformanceAgreement.objects.filter(period=period, employee=employee).exists():
        raise AgreementWorkflowError(f"{employee.employee_number} already has an agreement for {period.name}.")
    template = template or pick_template(period, employee)
    if template is None:
        raise AgreementWorkflowError(
            f"No published agreement template applies to {employee.employee_number} for {period.name}."
        )
    if template.status != AgreementTemplate.Status.PUBLISHED:
        raise AgreementWorkflowError("Agreements can only be created from a published template.")

    version = employee.current_version
    agreement = PerformanceAgreement.objects.create(
        period=period,
        employee=employee,
        head=version.manager if version else None,
        template=template,
        template_version=template.version,
    )
    for element in template.elements.select_related("section").all():
        AgreementElement.objects.create(
            agreement=agreement,
            section_title=element.section.title,
            section_order=element.section.order,
            kpa_description=element.kpa_description,
            kpi_title=element.kpi_title,
            metric=element.metric,
            weight=element.default_weight,
            level_descriptors=dict(element.level_descriptors or {}),
            order=element.order,
            locked=element.locked,
        )
    if actor is not None:
        log_access(
            actor=actor, action=AuditLogEntry.Action.CREATE, entity_type="performance.PerformanceAgreement",
            entity_id=agreement.pk, field_tier=FieldTier.SENSITIVE,
            fields_touched=f"created for {employee.employee_number} from template {template.name} v{template.version}",
        )
    return agreement


def generate_agreements_for_period(period: PerformancePeriod, *, actor=None) -> dict:
    """One agreement per active employee that a published template covers.
    Idempotent: employees who already have one are skipped, not duplicated."""
    created, skipped, no_template = 0, 0, []
    # Same "who counts as staff" rule as launch_review_cycle: anyone with a
    # current effective-dated version (terminations end it).
    for employee in Employee.objects.all():
        if employee.current_version is None:
            continue
        if PerformanceAgreement.objects.filter(period=period, employee=employee).exists():
            skipped += 1
            continue
        try:
            create_agreement(period=period, employee=employee, actor=actor)
        except AgreementWorkflowError:
            no_template.append(employee.employee_number)
            continue
        created += 1
    return {"created": created, "skipped": skipped, "no_template": no_template}


def validate_agreement_ready_to_submit(agreement: PerformanceAgreement) -> None:
    elements = list(agreement.elements.all())
    if not elements:
        raise AgreementWorkflowError("An agreement needs at least one KPI.")
    total = sum((e.weight for e in elements), Decimal("0"))
    if abs(total - Decimal("1")) > WEIGHT_TOLERANCE:
        raise AgreementWorkflowError(
            f"KPI weights must sum to 1.00 before submission (currently {total}). "
            "Adjust the weights so the scorecard totals 100%."
        )
    for element in elements:
        missing = REQUIRED_LEVELS - set(map(str, element.level_descriptors or {}))
        if missing:
            raise AgreementWorkflowError(
                f'"{element.kpi_title}" is missing target descriptors for level(s) {", ".join(sorted(missing))}.'
            )


def submit_agreement(agreement: PerformanceAgreement, *, actor: Employee) -> PerformanceAgreement:
    if agreement.status not in PerformanceAgreement.EDITABLE_STATUSES:
        raise AgreementWorkflowError("Only a draft or returned agreement can be submitted.", conflict=True)
    if actor.pk != agreement.employee_id:
        raise AgreementWorkflowError("Only the employee submits their own agreement for review.")
    validate_agreement_ready_to_submit(agreement)
    agreement.status = PerformanceAgreement.Status.SUBMITTED
    agreement.submitted_at = timezone.now()
    agreement.return_reason = ""
    agreement.save(update_fields=["status", "submitted_at", "return_reason"])
    return agreement


def return_agreement(agreement: PerformanceAgreement, *, actor: Employee, reason: str) -> PerformanceAgreement:
    if agreement.status != PerformanceAgreement.Status.SUBMITTED:
        raise AgreementWorkflowError("Only a submitted agreement can be returned.", conflict=True)
    if not (reason or "").strip():
        raise AgreementWorkflowError("A reason is required when returning an agreement for changes.")
    agreement.status = PerformanceAgreement.Status.RETURNED
    agreement.return_reason = reason.strip()
    agreement.save(update_fields=["status", "return_reason"])
    return agreement


def approve_agreement(agreement: PerformanceAgreement, *, actor: Employee) -> PerformanceAgreement:
    """The Head is happy with the content — signing can start (employee first)."""
    if agreement.status != PerformanceAgreement.Status.SUBMITTED:
        raise AgreementWorkflowError("Only a submitted agreement can be approved.", conflict=True)
    validate_agreement_ready_to_submit(agreement)
    agreement.status = PerformanceAgreement.Status.APPROVED
    agreement.save(update_fields=["status"])
    return agreement


@transaction.atomic
def amend_agreement(agreement: PerformanceAgreement, *, actor: Employee, reason: str) -> PerformanceAgreement:
    """Re-open a contracted agreement for changes: revision + 1, back to draft.
    Signatures of previous revisions stay (they are what was agreed then) —
    the workbook's Rev3/Rev4 counters, made real."""
    if agreement.status not in PerformanceAgreement.CONTRACTED_STATUSES:
        raise AgreementWorkflowError("Only a contracted agreement can be amended.", conflict=True)
    if not (reason or "").strip():
        raise AgreementWorkflowError("An amendment reason is required.")
    agreement.revision += 1
    agreement.status = PerformanceAgreement.Status.DRAFT
    agreement.amendment_reason = reason.strip()
    agreement.agreed_at = None
    agreement.save(update_fields=["revision", "status", "amendment_reason", "agreed_at"])
    log_access(
        actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type="performance.PerformanceAgreement",
        entity_id=agreement.pk, field_tier=FieldTier.SENSITIVE,
        fields_touched=f"amended to revision {agreement.revision}: {reason.strip()[:200]}",
    )
    return agreement


# --- signing ----------------------------------------------------------------


def active_delegation(head: Employee, delegate: Employee, *, on: date | None = None) -> SigningDelegation | None:
    on = on or timezone.localdate()
    for delegation in SigningDelegation.objects.filter(delegator=head, delegate=delegate, revoked_at__isnull=True):
        if delegation.is_active_on(on):
            return delegation
    return None


def may_sign_as_head(agreement: PerformanceAgreement, actor: Employee) -> bool:
    if agreement.head_id and actor.pk == agreement.head_id:
        return True
    return agreement.head_id is not None and active_delegation(agreement.head, actor) is not None


def _verify_identity(agreement: PerformanceAgreement, actor: Employee, *, password: str | None) -> str:
    """Proof of presence for the signature act. Password re-authentication by
    default (ECT Act ordinary electronic signature); a template may demand the
    ADR-009 TOTP step-up grant instead for higher-assurance populations."""
    method = agreement.template.signature_method
    if method == AgreementTemplate.SignatureMethod.TOTP:
        if not has_active_step_up_grant(actor, scope="payroll_data"):
            raise AgreementWorkflowError(
                "This scorecard requires authenticator (step-up) verification before signing."
            )
        return AgreementSignature.Method.TOTP
    if actor.user is None:
        raise AgreementWorkflowError("This employee has no login account and cannot sign electronically.")
    if not password or authenticate(username=actor.user.get_username(), password=password) is None:
        raise AgreementWorkflowError("Password confirmation failed — the signature was not recorded.")
    return AgreementSignature.Method.PASSWORD


def _snapshot_document(agreement: PerformanceAgreement, stage: str) -> AgreementDocument:
    """Generate (once per stage+revision) the exact PDF being signed."""
    existing = agreement.documents.filter(stage=stage, revision=agreement.revision).first()
    if existing is not None:
        return existing
    pdf_bytes = render_agreement_pdf(agreement, stage=stage)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    document = AgreementDocument(agreement=agreement, stage=stage, revision=agreement.revision, sha256=digest)
    document.pdf.save(
        f"agreement-{agreement.pk}-{stage}-rev{agreement.revision}.pdf", ContentFile(pdf_bytes), save=False
    )
    document.save()
    return document


@transaction.atomic
def sign_agreement(
    agreement: PerformanceAgreement,
    *,
    actor: Employee,
    role: str,
    password: str | None = None,
    ip_address: str | None = None,
    user_agent: str = "",
) -> AgreementSignature:
    """Record one signature. Order is enforced: employee first, then Head."""
    stage = agreement.current_stage
    if stage != PeriodPhase.Stage.CONTRACTING:
        raise AgreementWorkflowError("Only contracting-stage signing is implemented (mid-year/final land in PC-2).")

    # Authority first ("are you allowed to sign in this role at all"), then
    # duplication ("you already did"), then order ("not yet") — so the message
    # the caller gets is the most specific true one.
    if role == AgreementSignature.Role.EMPLOYEE:
        if actor.pk != agreement.employee_id:
            raise AgreementWorkflowError("Only the employee can sign as the employee.")
    elif role == AgreementSignature.Role.HEAD:
        if not may_sign_as_head(agreement, actor):
            raise AgreementWorkflowError("Only the Head (or an active delegate) can sign as the Head.")
    else:
        raise AgreementWorkflowError(f"Unknown signature role: {role}")

    if AgreementSignature.objects.filter(
        agreement=agreement, stage=stage, revision=agreement.revision, role=role
    ).exists():
        raise AgreementWorkflowError("That signature has already been recorded.", conflict=True)

    if role == AgreementSignature.Role.EMPLOYEE:
        if agreement.status != PerformanceAgreement.Status.APPROVED:
            raise AgreementWorkflowError(
                "The agreement must be reviewed and approved by your Head before you sign.", conflict=True
            )
    elif agreement.status != PerformanceAgreement.Status.EMPLOYEE_SIGNED:
        raise AgreementWorkflowError(
            "The employee signs first — you can sign once their signature is recorded.", conflict=True
        )

    method = _verify_identity(agreement, actor, password=password)
    document = _snapshot_document(agreement, stage)
    acting_for = None
    if role == AgreementSignature.Role.HEAD and actor.pk != agreement.head_id:
        acting_for = agreement.head

    signature = AgreementSignature.objects.create(
        agreement=agreement, stage=stage, revision=agreement.revision, role=role, signer=actor,
        acting_for=acting_for, method=method, document=document, document_sha256=document.sha256,
        ip_address=ip_address, user_agent=(user_agent or "")[:300],
    )

    if role == AgreementSignature.Role.EMPLOYEE:
        agreement.status = PerformanceAgreement.Status.EMPLOYEE_SIGNED
        agreement.save(update_fields=["status"])
    else:
        agreement.status = PerformanceAgreement.Status.AGREED
        agreement.agreed_at = timezone.now()
        agreement.save(update_fields=["status", "agreed_at"])

    log_access(
        actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type="performance.AgreementSignature",
        entity_id=signature.pk, field_tier=FieldTier.SENSITIVE, ip_address=ip_address,
        fields_touched=(
            f"{role} signature on agreement {agreement.pk} rev{agreement.revision} "
            f"({method}, sha256={document.sha256[:12]}…"
            + (f", acting for {acting_for.employee_number}" if acting_for else "")
            + ")"
        ),
    )
    return signature


# --- phases -----------------------------------------------------------------


def open_phase(period: PerformancePeriod, stage: str, *, actor=None) -> PerformancePeriod:
    """Move the period into a stage. Contracting also generates the agreements
    so there is something for the reminders to point at."""
    phase = period.phase(stage)
    if phase is None:
        raise AgreementWorkflowError(f"This period has no {stage} phase configured.")
    if stage == PeriodPhase.Stage.CONTRACTING:
        if period.status not in (PerformancePeriod.Status.DRAFT, PerformancePeriod.Status.CONTRACTING):
            raise AgreementWorkflowError("Contracting can only be opened on a draft period.", conflict=True)
        period.status = PerformancePeriod.Status.CONTRACTING
    elif stage == PeriodPhase.Stage.MIDYEAR:
        period.status = PerformancePeriod.Status.MIDYEAR
    else:
        period.status = PerformancePeriod.Status.FINAL
    period.save(update_fields=["status"])
    return period


def phase_deadline(period: PerformancePeriod, stage: str) -> date | None:
    phase = period.phase(stage)
    return phase.due_on if phase else None


def days_until(day: date | None, *, today: date | None = None) -> int | None:
    if day is None:
        return None
    return (day - (today or timezone.localdate())).days


def add_days(day: date, n: int) -> date:
    return day + timedelta(days=n)


__all__ = [
    "AgreementWorkflowError",
    "active_delegation",
    "add_days",
    "amend_agreement",
    "approve_agreement",
    "clone_period",
    "create_agreement",
    "days_until",
    "generate_agreements_for_period",
    "may_sign_as_head",
    "open_phase",
    "phase_deadline",
    "pick_template",
    "publish_template",
    "return_agreement",
    "sign_agreement",
    "submit_agreement",
    "validate_agreement_ready_to_submit",
]
