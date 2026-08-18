"""API for performance agreements (PC-1, ADR-010).

Every state change is a named action delegating to `services/agreements.py`;
the serializers are read-only for state fields so no PATCH can bypass the
workflow (the shape `ee_reporting.EEReport` already uses). `AgreementWorkflowError`
maps to 400, or 409 when the action was refused because of *order* — the Head
signing before the employee, a second signature, submitting something already
submitted — so the SPA can tell "you did it wrong" from "you did it too soon".
"""
from __future__ import annotations

from django.http import FileResponse
from django.utils import timezone
from rbac_audit.audit import log_access
from rbac_audit.drf import get_request_employee, int_query_param, row_scoped_queryset
from rbac_audit.models import AuditLogEntry
from rbac_audit.tiers import FieldTier
from rest_framework import mixins, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    AgreementDocument,
    AgreementElement,
    AgreementTemplate,
    PDPItem,
    PerformanceAgreement,
    PerformancePeriod,
    PeriodPhase,
    SigningDelegation,
    TemplateElement,
    TemplateSection,
)
from .permissions import (
    IsHRAdminOrReadOnlyForPerformance,
    PerformanceAgreementPermission,
    SigningDelegationPermission,
    can_read_all,
    can_view_agreement,
    is_admin,
    is_head_of,
)
from .serializers_agreements import (
    AgreementDocumentSerializer,
    AgreementElementSerializer,
    AgreementTemplateSerializer,
    PDPItemSerializer,
    PerformanceAgreementSerializer,
    PerformancePeriodSerializer,
    PeriodPhaseSerializer,
    ReasonSerializer,
    SigningDelegationSerializer,
    SignRequestSerializer,
    TemplateElementSerializer,
    TemplateSectionSerializer,
)
from .services import (
    AgreementWorkflowError,
    amend_agreement,
    approve_agreement,
    clone_period,
    create_agreement,
    generate_agreements_for_period,
    open_phase,
    publish_template,
    return_agreement,
    sign_agreement,
    submit_agreement,
)
from .services.agreements import may_sign_as_head


def _error(exc: AgreementWorkflowError) -> Response:
    return Response({"detail": str(exc)}, status=409 if getattr(exc, "conflict", False) else 400)


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class PerformancePeriodViewSet(viewsets.ModelViewSet):
    """Periods and their phase windows. Everyone reads (staff need their own
    deadlines); hr_admin writes."""

    queryset = PerformancePeriod.objects.prefetch_related("phases").all()
    serializer_class = PerformancePeriodSerializer
    permission_classes = [IsHRAdminOrReadOnlyForPerformance]

    def perform_create(self, serializer):
        serializer.save(created_by=get_request_employee(self.request))

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """Next FY from this one: dates +1 year, same windows and offsets."""
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"detail": "A name for the new period is required (e.g. 2027/28)."}, status=400)
        try:
            period = clone_period(self.get_object(), name=name, actor=get_request_employee(request))
        except AgreementWorkflowError as exc:
            return _error(exc)
        return Response(self.get_serializer(period).data, status=201)

    @action(detail=True, methods=["post"], url_path="open-phase")
    def open_phase_action(self, request, pk=None):
        stage = request.data.get("stage") or PeriodPhase.Stage.CONTRACTING
        period = self.get_object()
        try:
            open_phase(period, stage, actor=get_request_employee(request))
        except AgreementWorkflowError as exc:
            return _error(exc)
        period.refresh_from_db()
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=["post"], url_path="generate-agreements")
    def generate_agreements(self, request, pk=None):
        result = generate_agreements_for_period(self.get_object(), actor=get_request_employee(request))
        return Response(result, status=201 if result["created"] else 200)

    @action(detail=True, methods=["get"])
    def completion(self, request, pk=None):
        """Contracting progress for the hr_admin dashboard: overall and per division."""
        period = self.get_object()
        agreements = period.agreements.select_related("employee").all()
        signed_statuses = PerformanceAgreement.CONTRACTED_STATUSES
        by_division: dict[str, dict] = {}
        total = signed = outstanding = 0
        for agreement in agreements:
            version = agreement.employee.current_version
            division = getattr(version.department, "name", "Unassigned") if version else "Unassigned"
            bucket = by_division.setdefault(division, {"division": division, "total": 0, "signed": 0})
            bucket["total"] += 1
            total += 1
            if agreement.status in signed_statuses:
                bucket["signed"] += 1
                signed += 1
            else:
                outstanding += 1
        for bucket in by_division.values():
            bucket["completion_pct"] = round(100 * bucket["signed"] / bucket["total"], 1) if bucket["total"] else 0.0
        return Response({
            "period": period.name,
            "status": period.status,
            "total": total,
            "signed": signed,
            "outstanding": outstanding,
            "completion_pct": round(100 * signed / total, 1) if total else 0.0,
            "by_division": sorted(by_division.values(), key=lambda b: b["division"]),
        })


class PeriodPhaseViewSet(viewsets.ModelViewSet):
    queryset = PeriodPhase.objects.select_related("period").all()
    serializer_class = PeriodPhaseSerializer
    permission_classes = [IsHRAdminOrReadOnlyForPerformance]


class AgreementTemplateViewSet(viewsets.ModelViewSet):
    queryset = AgreementTemplate.objects.prefetch_related("sections__elements", "elements").all()
    serializer_class = AgreementTemplateSerializer
    permission_classes = [IsHRAdminOrReadOnlyForPerformance]

    def perform_create(self, serializer):
        serializer.save(created_by=get_request_employee(self.request))

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        try:
            template = publish_template(self.get_object(), actor=get_request_employee(request))
        except AgreementWorkflowError as exc:
            return _error(exc)
        return Response(self.get_serializer(template).data)

    @action(detail=True, methods=["post"], url_path="new-version")
    def new_version(self, request, pk=None):
        """Copy this template into a fresh draft version — the FY-to-FY edit
        path (the workbook changed shape between 2025/26 and 2026/27)."""
        source = self.get_object()
        clone = AgreementTemplate.objects.create(
            name=source.name,
            version=AgreementTemplate.objects.filter(name=source.name).order_by("-version").first().version + 1,
            period=source.period,
            rating_scale=dict(source.rating_scale),
            evidence_required=source.evidence_required,
            signature_method=source.signature_method,
            created_by=get_request_employee(request),
        )
        clone.job_grades.set(source.job_grades.all())
        clone.occupational_levels.set(source.occupational_levels.all())
        clone.departments.set(source.departments.all())
        section_map = {}
        for section in source.sections.all():
            section_map[section.id] = TemplateSection.objects.create(
                template=clone, title=section.title, order=section.order, locked=section.locked
            )
        for element in source.elements.all():
            TemplateElement.objects.create(
                template=clone, section=section_map[element.section_id], kpa_description=element.kpa_description,
                kpi_title=element.kpi_title, metric=element.metric, default_weight=element.default_weight,
                level_descriptors=dict(element.level_descriptors), order=element.order, locked=element.locked,
            )
        return Response(self.get_serializer(clone).data, status=201)


class TemplateSectionViewSet(viewsets.ModelViewSet):
    queryset = TemplateSection.objects.select_related("template").all()
    serializer_class = TemplateSectionSerializer
    permission_classes = [IsHRAdminOrReadOnlyForPerformance]


class TemplateElementViewSet(viewsets.ModelViewSet):
    queryset = TemplateElement.objects.select_related("template", "section").all()
    serializer_class = TemplateElementSerializer
    permission_classes = [IsHRAdminOrReadOnlyForPerformance]



class _HideForbiddenAsNotFound:
    """Someone else's scorecard answers 404, not 403 — a permission error on a
    detail route would otherwise confirm that a given employee has an agreement
    with that id. (The fast queryset no longer pre-filters detail lookups, so
    the object permission is what denies; this keeps the old 404 semantics.)"""

    def get_object(self):
        try:
            return super().get_object()
        except PermissionDenied as exc:
            raise NotFound from exc


class PerformanceAgreementViewSet(
    _HideForbiddenAsNotFound, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    """Read + named actions only. Creation happens through the period's
    `generate-agreements` action or `create` below (hr_admin), never a bare POST."""

    queryset = PerformanceAgreement.objects.select_related("employee", "head", "period", "template").prefetch_related(
        "elements", "pdp_items", "signatures", "documents"
    )
    serializer_class = PerformanceAgreementSerializer
    permission_classes = [PerformanceAgreementPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None:
            return qs.none()
        period_id = int_query_param(self.request, "period")
        if period_id is not None:
            qs = qs.filter(period_id=period_id)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        if self.request.query_params.get("hr_attention") == "true":
            qs = qs.filter(hr_attention=True)
        scope = self.request.query_params.get("scope")
        if scope == "mine":
            return qs.filter(employee=employee)
        if scope == "team":
            return qs.filter(head=employee)
        if can_read_all(employee):
            return qs
        # Detail routes (retrieve + every named action) resolve one object and
        # PerformanceAgreementPermission.has_object_permission decides — so
        # don't narrow here. Narrowing a *detail* lookup used to run
        # can_view_agreement over the whole table, i.e. a reporting-chain walk
        # per agreement: hundreds of queries per request, which stalled the
        # signature panel in the browser (caught by the PC-1 e2e run).
        if self.action not in ("list", "mine"):
            return qs
        # Lists: their own + anyone their row scope covers (the shared
        # own_team/self helper) + agreements they are an active signing
        # delegate for. One pass over the org chart, not one per row.
        scoped = row_scoped_queryset(qs, employee)
        delegated_heads = SigningDelegation.objects.filter(
            delegate=employee, revoked_at__isnull=True, start_date__lte=timezone.localdate(),
            end_date__gte=timezone.localdate(),
        ).values_list("delegator_id", flat=True)
        return (scoped | qs.filter(employee=employee) | qs.filter(head_id__in=list(delegated_heads))).distinct()

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        employee = get_request_employee(request)
        agreements = self.get_queryset().filter(employee=employee).order_by("-period__start_date")
        return Response(self.get_serializer(agreements, many=True).data)

    @action(detail=False, methods=["post"])
    def create_for(self, request):
        """hr_admin creates one agreement for one employee (the exception path:
        a late joiner after the bulk generate)."""
        actor = get_request_employee(request)
        if not is_admin(actor):
            return Response({"detail": "Only hr_admin can create an agreement directly."}, status=403)
        try:
            period = PerformancePeriod.objects.get(pk=request.data.get("period"))
            from core_hr.models import Employee

            employee = Employee.objects.get(pk=request.data.get("employee"))
        except (PerformancePeriod.DoesNotExist, ValueError, TypeError):
            return Response({"detail": "A valid period id is required."}, status=400)
        except Exception:
            return Response({"detail": "A valid employee id is required."}, status=400)
        try:
            agreement = create_agreement(period=period, employee=employee, actor=actor)
        except AgreementWorkflowError as exc:
            return _error(exc)
        return Response(self.get_serializer(agreement).data, status=201)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        agreement = self.get_object()
        try:
            submit_agreement(agreement, actor=get_request_employee(request))
        except AgreementWorkflowError as exc:
            return _error(exc)
        agreement.refresh_from_db()
        return Response(self.get_serializer(agreement).data)

    @action(detail=True, methods=["post"], url_path="return")
    def return_for_changes(self, request, pk=None):
        agreement = self.get_object()
        actor = get_request_employee(request)
        if not (is_head_of(agreement, actor) or is_admin(actor)):
            return Response({"detail": "Only the Head (or hr_admin) can return an agreement."}, status=403)
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            return_agreement(agreement, actor=actor, reason=payload.validated_data["reason"])
        except AgreementWorkflowError as exc:
            return _error(exc)
        agreement.refresh_from_db()
        return Response(self.get_serializer(agreement).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        agreement = self.get_object()
        actor = get_request_employee(request)
        if not (is_head_of(agreement, actor) or is_admin(actor)):
            return Response({"detail": "Only the Head (or hr_admin) can approve an agreement."}, status=403)
        try:
            approve_agreement(agreement, actor=actor)
        except AgreementWorkflowError as exc:
            return _error(exc)
        agreement.refresh_from_db()
        return Response(self.get_serializer(agreement).data)

    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        agreement = self.get_object()
        payload = SignRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            sign_agreement(
                agreement,
                actor=get_request_employee(request),
                role=payload.validated_data["role"],
                password=payload.validated_data.get("password"),
                ip_address=_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        except AgreementWorkflowError as exc:
            return _error(exc)
        agreement.refresh_from_db()
        return Response(self.get_serializer(agreement).data)

    @action(detail=True, methods=["post"])
    def amend(self, request, pk=None):
        agreement = self.get_object()
        actor = get_request_employee(request)
        if not (is_head_of(agreement, actor) or is_admin(actor) or agreement.employee_id == actor.pk):
            return Response({"detail": "Only the employee, their Head, or hr_admin can amend an agreement."}, status=403)
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            amend_agreement(agreement, actor=actor, reason=payload.validated_data["reason"])
        except AgreementWorkflowError as exc:
            return _error(exc)
        agreement.refresh_from_db()
        return Response(self.get_serializer(agreement).data)

    @action(detail=True, methods=["get"], url_path="can-sign")
    def can_sign(self, request, pk=None):
        """What the SPA needs to render the signature panel honestly: which
        button to enable, and *why* the other one is disabled."""
        agreement = self.get_object()
        actor = get_request_employee(request)
        employee_signed = agreement.signatures.filter(
            stage=agreement.current_stage, revision=agreement.revision, role="employee"
        ).exists()
        as_employee = agreement.employee_id == actor.pk and agreement.status == PerformanceAgreement.Status.APPROVED
        as_head = may_sign_as_head(agreement, actor) and agreement.status == PerformanceAgreement.Status.EMPLOYEE_SIGNED
        blocked = ""
        if may_sign_as_head(agreement, actor) and not as_head and not employee_signed:
            blocked = "The employee signs first — you can sign once their signature is recorded."
        return Response({
            "as_employee": as_employee,
            "as_head": as_head,
            "employee_signed": employee_signed,
            "acting_for_head": bool(agreement.head_id and agreement.head_id != actor.pk and as_head),
            "method": agreement.template.signature_method,
            "blocked_reason": blocked,
        })

    @action(detail=True, methods=["get"], url_path="documents/(?P<document_id>[0-9]+)/download")
    def download_document(self, request, pk=None, document_id=None):
        agreement = self.get_object()
        document = AgreementDocument.objects.filter(agreement=agreement, pk=document_id).first()
        if document is None or not document.pdf:
            return Response({"detail": "Not found."}, status=404)
        log_access(
            actor=get_request_employee(request), action=AuditLogEntry.Action.EXPORT,
            entity_type="performance.AgreementDocument", entity_id=document.pk, field_tier=FieldTier.SENSITIVE,
            fields_touched=f"downloaded signed agreement {agreement.pk} {document.stage} rev{document.revision}",
        )
        return FileResponse(
            document.pdf.open("rb"), as_attachment=True,
            filename=f"scorecard-{agreement.employee.employee_number}-{agreement.period.name.replace('/', '-')}-{document.stage}.pdf",
        )


class AgreementElementViewSet(_HideForbiddenAsNotFound, viewsets.ModelViewSet):
    queryset = AgreementElement.objects.select_related("agreement", "agreement__employee", "agreement__head").all()
    serializer_class = AgreementElementSerializer
    permission_classes = [PerformanceAgreementPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None:
            return qs.none()
        agreement_id = int_query_param(self.request, "agreement")
        if agreement_id is not None:
            qs = qs.filter(agreement_id=agreement_id)
        if can_read_all(employee):
            return qs
        if self.action != "list":
            return qs  # object permission decides; see PerformanceAgreementViewSet.get_queryset
        visible = PerformanceAgreement.objects.filter(
            pk__in=row_scoped_queryset(PerformanceAgreement.objects.all(), employee).values("pk")
        ) | PerformanceAgreement.objects.filter(employee=employee)
        return qs.filter(agreement__in=visible.distinct())

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj.agreement)


class PDPItemViewSet(_HideForbiddenAsNotFound, viewsets.ModelViewSet):
    queryset = PDPItem.objects.select_related("agreement", "agreement__employee", "agreement__head").all()
    serializer_class = PDPItemSerializer
    permission_classes = [PerformanceAgreementPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None:
            return qs.none()
        agreement_id = int_query_param(self.request, "agreement")
        if agreement_id is not None:
            qs = qs.filter(agreement_id=agreement_id)
        if can_read_all(employee):
            return qs
        if self.action != "list":
            return qs  # object permission decides; see PerformanceAgreementViewSet.get_queryset
        visible = PerformanceAgreement.objects.filter(
            pk__in=row_scoped_queryset(PerformanceAgreement.objects.all(), employee).values("pk")
        ) | PerformanceAgreement.objects.filter(employee=employee)
        return qs.filter(agreement__in=visible.distinct())

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj.agreement)


class SigningDelegationViewSet(viewsets.ModelViewSet):
    queryset = SigningDelegation.objects.select_related("delegator", "delegate").all()
    serializer_class = SigningDelegationSerializer
    permission_classes = [SigningDelegationPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if employee is None:
            return qs.none()
        if can_read_all(employee):
            return qs
        return qs.filter(delegator=employee) | qs.filter(delegate=employee)

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        delegator = serializer.validated_data.get("delegator")
        if delegator is not None and delegator.pk != actor.pk and not is_admin(actor):
            raise PermissionError
        delegation = serializer.save(created_by=actor)
        log_access(
            actor=actor, action=AuditLogEntry.Action.PERMISSION_CHANGE, entity_type="performance.SigningDelegation",
            entity_id=delegation.pk, field_tier=FieldTier.INTERNAL,
            fields_touched=(
                f"{delegation.delegator.employee_number} delegated performance signing to "
                f"{delegation.delegate.employee_number} for {delegation.start_date}–{delegation.end_date}"
            ),
        )

    def handle_exception(self, exc):
        if isinstance(exc, PermissionError):
            return Response({"detail": "You can only delegate your own signing authority."}, status=403)
        return super().handle_exception(exc)
