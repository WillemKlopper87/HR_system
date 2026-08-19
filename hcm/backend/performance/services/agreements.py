"""Performance-agreement workflow (PC-1, ADR-010).

The state machine lives here, not in views, so every route into it (API,
management command, future import) obeys the same rules:

    draft ──submit(employee)──▶ submitted ──return(head)──▶ returned ──submit──▶ …
                                    └─approve(head)─▶ approved
    approved ──sign(employee)──▶ employee_signed ──sign(head|delegate)──▶ agreed

Mid-year (Q2) and final (Q4) reviews (PC-2) are the same two-signature shape,
just without a submit/approve/return step first — the period phase opening is
what makes the stage "open" for editing and signing:

    agreed ──open(midyear)──▶ midyear_open ──sign(employee)──▶ midyear_employee_signed
           ──sign(head|delegate)──▶ midyear_signed ──open(final)──▶ final_open ── … ──▶ final_signed

`STAGE_FLOW` below is the one table every stage's submit/sign logic reads from,
so contracting/mid-year/final can never quietly drift out of sync with each
other.

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
    EvidenceItem,
    PDPItem,
    PerformanceAgreement,
    PerformancePeriod,
    PeriodPhase,
    Review,
    SigningDelegation,
)
from ..models.agreements import RATING_MAX, RATING_MIN
from ..pdf import render_agreement_pdf

WEIGHT_TOLERANCE = Decimal("0.0005")
REQUIRED_LEVELS = {"1", "2", "3", "4", "5"}

# One row per stage: which status means "open for signing", what each role's
# signature moves it to, and the message an early employee-side attempt gets.
# sign_agreement() and the can-sign view both read this — the single source
# of truth for "who may sign what, in what order" across all three stages.
STAGE_FLOW = {
    PeriodPhase.Stage.CONTRACTING: {
        "open_status": PerformanceAgreement.Status.APPROVED,
        "employee_signed_status": PerformanceAgreement.Status.EMPLOYEE_SIGNED,
        "head_signed_status": PerformanceAgreement.Status.AGREED,
        "employee_error": "The agreement must be reviewed and approved by your Head before you sign.",
    },
    PeriodPhase.Stage.MIDYEAR: {
        "open_status": PerformanceAgreement.Status.MIDYEAR_OPEN,
        "employee_signed_status": PerformanceAgreement.Status.MIDYEAR_EMPLOYEE_SIGNED,
        "head_signed_status": PerformanceAgreement.Status.MIDYEAR_SIGNED,
        "employee_error": "The mid-year review isn't open yet — it opens once HR starts the Q2 phase.",
    },
    PeriodPhase.Stage.FINAL: {
        "open_status": PerformanceAgreement.Status.FINAL_OPEN,
        "employee_signed_status": PerformanceAgreement.Status.FINAL_EMPLOYEE_SIGNED,
        "head_signed_status": PerformanceAgreement.Status.FINAL_SIGNED,
        "employee_error": "The final assessment isn't open yet — it opens once HR starts the Q4 phase.",
    },
}

# Which AgreementElement fields belong to which stage, and therefore when they
# may be edited: only while the agreement sits exactly at that stage's
# open_status (mirrors "contracting content freezes once out of draft" —
# see AgreementElementSerializer.validate()).
STAGE_ELEMENT_FIELDS = {
    PeriodPhase.Stage.MIDYEAR: {"q2_target_note", "q2_employee_comment", "q2_head_comment"},
    PeriodPhase.Stage.FINAL: {"final_rating", "final_employee_comment", "final_head_comment"},
}

# The Head's own field for each stage stays open one status later than the
# rest -- through *_employee_signed -- so the Head can add their comment
# after the employee has signed but before the Head signs themself, mirroring
# how contracting lets the Head act (approve/return) on what the employee
# already submitted. AgreementElementSerializer.validate() is the real gate.
STAGE_HEAD_FIELDS = {
    PeriodPhase.Stage.MIDYEAR: {"q2_head_comment"},
    PeriodPhase.Stage.FINAL: {"final_head_comment"},
}


_STAGE_COMPLETE_STATUSES = {
    PerformanceAgreement.Status.AGREED,
    PerformanceAgreement.Status.MIDYEAR_SIGNED,
    PerformanceAgreement.Status.FINAL_SIGNED,
    PerformanceAgreement.Status.ARCHIVED,
}


def active_stage_for(agreement: PerformanceAgreement) -> str | None:
    """Same three-way split as `current_stage` (the display property), except
    the moment a stage is *fully* signed off (AGREED / MIDYEAR_SIGNED /
    FINAL_SIGNED / ARCHIVED) this returns None instead of naming the stage
    that just finished: there is nothing left to sign until the next phase
    opens, and reusing the just-completed stage's name is what caused a
    signing attempt in that gap to read as a duplicate of the stage that
    already closed rather than "nothing is open right now". Every other
    status (including SUBMITTED/RETURNED/APPROVED, which aren't literally
    an *_open status but are still meaningfully "in the contracting stage")
    keeps `current_stage`'s answer, so sign_agreement's per-stage error
    messages stay exactly as specific as before this existed."""
    if agreement.status in _STAGE_COMPLETE_STATUSES:
        return None
    return agreement.current_stage


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
def stage_is_signed(agreement: PerformanceAgreement, stage: str, *, revision: int | None = None) -> bool:
    """True once the Head's signature exists for that stage+revision — the
    point past which evidence for that stage may no longer be deleted and new
    evidence is flagged `added_after_signoff`."""
    revision = agreement.revision if revision is None else revision
    return AgreementSignature.objects.filter(
        agreement=agreement, stage=stage, revision=revision, role=AgreementSignature.Role.HEAD
    ).exists()


def validate_final_ratings_complete(agreement: PerformanceAgreement) -> None:
    """Every KPI needs a rating before the final stage can be signed off --
    the same completeness principle as contracting's weight/descriptor check
    (validate_agreement_ready_to_submit). Without this an unrated KPI would
    silently score as 0 in the weighted sum instead of blocking sign-off."""
    unrated = [e.kpi_title for e in agreement.elements.all() if e.final_rating is None]
    if unrated:
        raise AgreementWorkflowError(
            "Every KPI needs a rating before you can sign off: " + ", ".join(unrated)
        )


def validate_evidence_for_final(agreement: PerformanceAgreement) -> None:
    """Gate the FINAL stage's employee signature on evidence, but only when
    the template opted into that (`evidence_required`) — by default evidence
    is optional-but-visible, never a hard gate (user, investigation §6)."""
    if not agreement.template.evidence_required:
        return
    missing = [
        e.kpi_title
        for e in agreement.elements.all()
        if e.final_rating is not None and not e.evidence_items.exists()
    ]
    if missing:
        raise AgreementWorkflowError(
            "This template requires evidence before signing off: " + ", ".join(missing)
        )


def _finalize_scoring(agreement: PerformanceAgreement) -> None:
    """Σ(weight × rating) over every rated element, frozen onto the agreement
    at the moment the Head signs the final stage. Also decides `hr_attention`:
    the user's rule is "3 = doing your job" — below that on the overall score
    *or* on any individual KPI is worth HR's attention (KPI-Contracting-
    Investigation.md §6 flagged this as "to be confirmed"; both are checked
    until told otherwise, and the reason says which)."""
    threshold = agreement.period.attention_threshold
    elements = list(agreement.elements.all())
    total = sum((e.score for e in elements if e.score is not None), Decimal("0"))
    agreement.final_score = total.quantize(Decimal("0.01"))

    reasons = []
    if agreement.final_score < threshold:
        reasons.append(f"overall score {agreement.final_score} is below {threshold}")
    low_kpis = [e.kpi_title for e in elements if e.final_rating is not None and Decimal(e.final_rating) < threshold]
    if low_kpis:
        reasons.append(f"KPI rating below {threshold}: {', '.join(low_kpis)}")
    agreement.hr_attention = bool(reasons)
    agreement.hr_attention_reason = "; ".join(reasons)[:300]


def sync_legacy_review(agreement: PerformanceAgreement) -> Review | None:
    """Mirrors the final score onto the Sprint 6-7 `Review` row so the pages
    built on it keep showing something real while they're still around (they
    retire in PC-3). No-op if this period was never linked to a legacy cycle
    — new periods don't need one. `Review` has one self_rating and one
    manager_rating; the agreement has a single, jointly-agreed final_rating
    per KPI, so both sides of the legacy record get the same rounded overall
    score rather than inventing a second number that was never actually
    collected."""
    period = agreement.period
    if period.legacy_cycle_id is None or agreement.final_score is None:
        return None
    review, _ = Review.objects.get_or_create(
        review_cycle_id=period.legacy_cycle_id, employee=agreement.employee, defaults={"manager": agreement.head}
    )
    rating = int(min(RATING_MAX, max(RATING_MIN, round(agreement.final_score))))
    review.manager = agreement.head
    review.self_rating = rating
    review.manager_rating = rating
    employee_sig = agreement.signatures.filter(
        stage=PeriodPhase.Stage.FINAL, role=AgreementSignature.Role.EMPLOYEE, revision=agreement.revision
    ).first()
    head_sig = agreement.signatures.filter(
        stage=PeriodPhase.Stage.FINAL, role=AgreementSignature.Role.HEAD, revision=agreement.revision
    ).first()
    if employee_sig:
        review.self_submitted_at = employee_sig.signed_at
    if head_sig:
        review.manager_submitted_at = head_sig.signed_at
    review.save()
    return review


def sign_agreement(
    agreement: PerformanceAgreement,
    *,
    actor: Employee,
    role: str,
    password: str | None = None,
    ip_address: str | None = None,
    user_agent: str = "",
) -> AgreementSignature:
    """Record one signature. Order is enforced: employee first, then Head —
    for whichever stage (contracting/mid-year/final) the agreement is
    currently at; see STAGE_FLOW for the per-stage status table."""
    # Authority first ("are you allowed to sign in this role at all") —
    # stage-independent, so this must run before stage resolution: someone
    # who was never allowed to sign gets that specific 400, never a generic
    # "nothing open" 409 that would (a) leak stage-timing details to them and
    # (b) contradict what an authorised signer sees for the same agreement.
    if role == AgreementSignature.Role.EMPLOYEE:
        if actor.pk != agreement.employee_id:
            raise AgreementWorkflowError("Only the employee can sign as the employee.")
    elif role == AgreementSignature.Role.HEAD:
        if not may_sign_as_head(agreement, actor):
            raise AgreementWorkflowError("Only the Head (or an active delegate) can sign as the Head.")
    else:
        raise AgreementWorkflowError(f"Unknown signature role: {role}")

    # Then: is there even a stage open to act on right now, then duplication
    # ("you already did"), then order ("not yet") — so the message the
    # caller gets is the most specific true one.
    stage = active_stage_for(agreement)
    if stage is None:
        raise AgreementWorkflowError(
            "There is nothing open to sign on this agreement right now.", conflict=True
        )
    flow = STAGE_FLOW[stage]

    if AgreementSignature.objects.filter(
        agreement=agreement, stage=stage, revision=agreement.revision, role=role
    ).exists():
        raise AgreementWorkflowError("That signature has already been recorded.", conflict=True)

    if role == AgreementSignature.Role.EMPLOYEE:
        if agreement.status != flow["open_status"]:
            raise AgreementWorkflowError(flow["employee_error"], conflict=True)
        if stage == PeriodPhase.Stage.FINAL:
            validate_final_ratings_complete(agreement)
            validate_evidence_for_final(agreement)
    elif agreement.status != flow["employee_signed_status"]:
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

    update_fields = ["status"]
    if role == AgreementSignature.Role.EMPLOYEE:
        agreement.status = flow["employee_signed_status"]
    else:
        agreement.status = flow["head_signed_status"]
        if stage == PeriodPhase.Stage.CONTRACTING:
            agreement.agreed_at = timezone.now()
            update_fields.append("agreed_at")
        elif stage == PeriodPhase.Stage.FINAL:
            _finalize_scoring(agreement)
            update_fields += ["final_score", "hr_attention", "hr_attention_reason"]
    agreement.save(update_fields=update_fields)
    if role == AgreementSignature.Role.HEAD and stage == PeriodPhase.Stage.FINAL:
        sync_legacy_review(agreement)

    log_access(
        actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type="performance.AgreementSignature",
        entity_id=signature.pk, field_tier=FieldTier.SENSITIVE, ip_address=ip_address,
        fields_touched=(
            f"{role} signature on agreement {agreement.pk} rev{agreement.revision} [{stage}] "
            f"({method}, sha256={document.sha256[:12]}…"
            + (f", acting for {acting_for.employee_number}" if acting_for else "")
            + ")"
        ),
    )
    return signature


# --- phases -----------------------------------------------------------------


def open_phase(period: PerformancePeriod, stage: str, *, actor=None) -> PerformancePeriod:
    """Move the period into a stage. Contracting also generates the agreements
    so there is something for the reminders to point at; mid-year/final also
    carry every eligible agreement forward into that stage's *_open status —
    otherwise "the phase is open" would be a period-level fact with no effect
    on any individual scorecard."""
    phase = period.phase(stage)
    if phase is None:
        raise AgreementWorkflowError(f"This period has no {stage} phase configured.")
    if stage == PeriodPhase.Stage.CONTRACTING:
        if period.status not in (PerformancePeriod.Status.DRAFT, PerformancePeriod.Status.CONTRACTING):
            raise AgreementWorkflowError("Contracting can only be opened on a draft period.", conflict=True)
        period.status = PerformancePeriod.Status.CONTRACTING
    elif stage == PeriodPhase.Stage.MIDYEAR:
        period.status = PerformancePeriod.Status.MIDYEAR
        PerformanceAgreement.objects.filter(
            period=period, status=PerformanceAgreement.Status.AGREED
        ).update(status=PerformanceAgreement.Status.MIDYEAR_OPEN)
    else:
        period.status = PerformancePeriod.Status.FINAL
        # Whichever of the two contracted "ready" states an agreement is in —
        # mid-year genuinely happened (MIDYEAR_SIGNED) or it didn't
        # (still AGREED, e.g. this org skipped Q2 this year) — both are
        # legitimate starting points for the final assessment.
        PerformanceAgreement.objects.filter(
            period=period,
            status__in=[PerformanceAgreement.Status.AGREED, PerformanceAgreement.Status.MIDYEAR_SIGNED],
        ).update(status=PerformanceAgreement.Status.FINAL_OPEN)
    period.save(update_fields=["status"])
    return period


def archive_period(period: PerformancePeriod, *, actor=None) -> dict:
    """Close out a financial year (PC-3). Deliberately permissive rather than
    all-or-nothing: whichever agreements genuinely finished the year
    (FINAL_SIGNED) move to ARCHIVED; anyone who never got there (a straggler,
    a late joiner) is left exactly where they are and counted as
    `outstanding` in the response, the same "report, don't block" shape as
    `generate_agreements_for_period`. The period itself always moves to
    ARCHIVED -- a real FY doesn't stay open forever waiting for one holdout,
    and `current_stage`/`stage_is_signed` already treat ARCHIVED as terminal."""
    archived = PerformanceAgreement.objects.filter(
        period=period, status=PerformanceAgreement.Status.FINAL_SIGNED
    ).update(status=PerformanceAgreement.Status.ARCHIVED)
    outstanding = period.agreements.exclude(
        status__in=[PerformanceAgreement.Status.FINAL_SIGNED, PerformanceAgreement.Status.ARCHIVED]
    ).count()
    period.status = PerformancePeriod.Status.ARCHIVED
    period.save(update_fields=["status"])
    if actor is not None:
        log_access(
            actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type="performance.PerformancePeriod",
            entity_id=period.pk, field_tier=FieldTier.INTERNAL,
            fields_touched=f"archived: {archived} agreement(s) archived, {outstanding} left outstanding",
        )
    return {"archived": archived, "outstanding": outstanding}


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
    "STAGE_ELEMENT_FIELDS",
    "STAGE_FLOW",
    "STAGE_HEAD_FIELDS",
    "AgreementWorkflowError",
    "active_delegation",
    "active_stage_for",
    "add_days",
    "amend_agreement",
    "approve_agreement",
    "archive_period",
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
    "stage_is_signed",
    "submit_agreement",
    "sync_legacy_review",
    "validate_agreement_ready_to_submit",
    "validate_evidence_for_final",
    "validate_final_ratings_complete",
]
