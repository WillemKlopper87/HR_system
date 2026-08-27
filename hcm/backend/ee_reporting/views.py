from __future__ import annotations

import os

from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rbac_audit.audit import log_access
from rbac_audit.drf import get_request_employee, int_query_param
from rbac_audit.models import AuditLogEntry
from rbac_audit.permissions import can_see_unsuppressed_aggregates, has_role
from rbac_audit.stepup import RequiresPayrollStepUp
from rbac_audit.tiers import FieldTier
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from . import export
from .dashboards import _suppress_matrix
from .models import (
    EEForumMeeting,
    EEForumMember,
    EEPlan,
    EEPlanMeasure,
    EEPlanProgressSnapshot,
    EEQuestionnaire,
    EEReport,
    EESector,
    EmployerConfig,
    RemunerationRecord,
)
from .permissions import (
    EEForumPermission,
    EEOperationalPermission,
    EEReportingPermission,
    RemunerationRecordPermission,
    is_ee_reader,
)
from .serializers import (
    EEForumMeetingSerializer,
    EEForumMemberSerializer,
    EEPlanMeasureSerializer,
    EEPlanProgressSnapshotSerializer,
    EEPlanSerializer,
    EEQuestionnaireSerializer,
    EEReportSerializer,
    EESectorSerializer,
    EmployerConfigSerializer,
    GenerateReportSerializer,
    RemunerationRecordSerializer,
    SignOffSerializer,
    TakeSnapshotSerializer,
)
from .services import (
    ApprovalError,
    RemunerationImportError,
    ReportNotReadyError,
    ee_manager_approve,
    forum_composition,
    generate_report,
    import_remuneration_csv,
    sector_target_defaults,
    sign_off,
    submit_for_review,
    take_progress_snapshot,
)
from .uploads import MinutesValidationError, validate_minutes_upload
from .validation import validate_report_data


def _require_hr_admin(actor, message):
    """EEReportingPermission's has_permission is deliberately coarse
    (any of hr_admin/ee_manager/accounting_officer may reach a POST, so
    ee_review/sign_off's OWN role checks below aren't blocked upstream —
    see permissions.py). Actions that really are hr_admin-only (config/
    plan/questionnaire writes, generate, submit, CSV import) enforce that
    narrower rule here instead."""
    if not has_role(actor, "hr_admin"):
        raise PermissionDenied(message)


class EESectorViewSet(viewsets.ReadOnlyModelViewSet):
    """The EEA17 sector table (Gazette 52514) — reference data, not
    editable through the API; seeded by migration 0005."""

    queryset = EESector.objects.all()
    serializer_class = EESectorSerializer
    permission_classes = [EEReportingPermission]


class EmployerConfigViewSet(viewsets.ModelViewSet):
    queryset = EmployerConfig.objects.all()
    serializer_class = EmployerConfigSerializer
    permission_classes = [EEReportingPermission]

    def perform_create(self, serializer):
        _require_hr_admin(get_request_employee(self.request), "Only hr_admin can edit the employer configuration.")
        serializer.save()

    def perform_update(self, serializer):
        _require_hr_admin(get_request_employee(self.request), "Only hr_admin can edit the employer configuration.")
        serializer.save()


class EEPlanViewSet(viewsets.ModelViewSet):
    queryset = EEPlan.objects.all()
    serializer_class = EEPlanSerializer
    permission_classes = [EEReportingPermission]

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        _require_hr_admin(actor, "Only hr_admin can edit the EE Plan.")
        serializer.save(created_by=actor)

    def perform_update(self, serializer):
        _require_hr_admin(get_request_employee(self.request), "Only hr_admin can edit the EE Plan.")
        serializer.save()

    @action(detail=False, methods=["get"])
    def sector_defaults(self, request):
        """sector_targets/disability_5yr_target_pct pre-filled from a
        gazetted EESector, for the plan form to offer before the user
        types a single percentage by hand. `?sector=<id>` picks the
        sector explicitly; otherwise falls back to the employer
        configuration's own sector (reg. 9(7))."""
        sector_id = int_query_param(request, "sector")
        sector = (
            EESector.objects.filter(pk=sector_id).first()
            if sector_id is not None
            else (EmployerConfig.objects.first() or EmployerConfig()).sector
        )
        if sector is None:
            return Response({"detail": "No sector specified and the employer configuration has none set."}, status=404)
        return Response(sector_target_defaults(sector))


class EEQuestionnaireViewSet(viewsets.ModelViewSet):
    queryset = EEQuestionnaire.objects.all()
    serializer_class = EEQuestionnaireSerializer
    permission_classes = [EEReportingPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        report_year = int_query_param(self.request, "report_year")
        if report_year is not None:
            qs = qs.filter(report_year=report_year)
        return qs

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        _require_hr_admin(actor, "Only hr_admin can edit the EE questionnaire.")
        serializer.save(updated_by=actor)

    def perform_update(self, serializer):
        actor = get_request_employee(self.request)
        _require_hr_admin(actor, "Only hr_admin can edit the EE questionnaire.")
        serializer.save(updated_by=actor)


class RemunerationRecordViewSet(viewsets.ModelViewSet):
    """No PATCH/PUT — records are only ever created via CSV import
    (import_csv, which upserts) so there's no reason to hand-edit one.
    RequiresPayrollStepUp: unlike EEReport (Sensitive-tier aggregated
    snapshots), remuneration_record is Data-Dictionary.md's literal
    per-employee payroll figures ("imported from SAP payroll") — Restricted
    tier, same step-up bar as compensation.PayBand/CompProposal. Report
    *generation* (services.py::generate_report) reads this table directly
    at the ORM layer, not through this viewset, so a signed-off EEA4 isn't
    blocked by whether anyone currently holds a step-up grant."""

    queryset = RemunerationRecord.objects.select_related("employee")
    serializer_class = RemunerationRecordSerializer
    permission_classes = [RemunerationRecordPermission, RequiresPayrollStepUp]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        period_start = self.request.query_params.get("period_start")
        period_end = self.request.query_params.get("period_end")
        if period_start:
            qs = qs.filter(period_start=period_start)
        if period_end:
            qs = qs.filter(period_end=period_end)
        return qs

    @action(detail=False, methods=["post"])
    def import_csv(self, request):
        _require_hr_admin(get_request_employee(request), "Only hr_admin can import remuneration records.")
        csv_text = request.data.get("csv") if isinstance(request.data, dict) else None
        if not csv_text and request.FILES.get("file"):
            csv_text = request.FILES["file"].read().decode("utf-8-sig")
        if not csv_text:
            return Response({"detail": "No CSV content provided (expected 'csv' text or a 'file' upload)."}, status=400)
        try:
            result = import_remuneration_csv(csv_text, actor=get_request_employee(request))
        except RemunerationImportError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(result, status=201 if result["created"] else 200)


class EEReportViewSet(viewsets.ModelViewSet):
    """No direct create/update — every mutation goes through a named
    action (generate/submit_for_review/ee_review/sign_off) so the
    state-machine rules in services.py are the only way through, never a
    raw PATCH that could bypass them."""

    queryset = EEReport.objects.select_related("generated_by", "ee_reviewed_by", "signed_off_by")
    serializer_class = EEReportSerializer
    permission_classes = [EEReportingPermission]
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        # "post" stays in http_method_names for the named actions below, so
        # the base create() must be shut explicitly — otherwise an empty POST
        # reaches an all-read-only serializer and crashes with a 500
        # IntegrityError (found by the H2 access-matrix sweep).
        return Response({"detail": 'Method "POST" not allowed — use /generate/.'}, status=405)

    def get_queryset(self):
        qs = super().get_queryset()
        for param in ("form_type", "status"):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{param: value})
        report_year = int_query_param(self.request, "report_year")
        if report_year is not None:
            qs = qs.filter(report_year=report_year)
        return qs

    @action(detail=False, methods=["post"])
    def generate(self, request):
        actor = get_request_employee(request)
        _require_hr_admin(actor, "Only hr_admin can generate a report.")
        input_serializer = GenerateReportSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            report = generate_report(actor=actor, **input_serializer.validated_data)
        except ReportNotReadyError as exc:
            return Response({"detail": str(exc), "issues": exc.issues}, status=400)
        return Response(self.get_serializer(report).data, status=201)

    @action(detail=True, methods=["post"])
    def submit_for_review(self, request, pk=None):
        actor = get_request_employee(request)
        _require_hr_admin(actor, "Only hr_admin can submit a report for EE manager review.")
        report = self.get_object()
        try:
            submit_for_review(report, actor=actor)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=["post"])
    def ee_review(self, request, pk=None):
        actor = get_request_employee(request)
        if not has_role(actor, "ee_manager"):
            raise PermissionDenied("Only ee_manager can approve at the EE-manager review step.")
        report = self.get_object()
        try:
            ee_manager_approve(report, actor=actor)
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=["post"])
    def sign_off(self, request, pk=None):
        actor = get_request_employee(request)
        if not has_role(actor, "accounting_officer"):
            raise PermissionDenied("Only the accounting_officer can sign off a report.")
        input_serializer = SignOffSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        report = self.get_object()
        try:
            sign_off(report, actor=actor, place=input_serializer.validated_data.get("place", ""))
        except ApprovalError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(report).data)

    @action(detail=True, methods=["get"])
    def validate(self, request, pk=None):
        """Cell-by-cell check of this generated snapshot against
        EEA-Form-Spec-Notes.md's validation-engine rules — advisory, not a
        state-machine gate (unlike validate_report_readiness, which blocks
        generation itself): a reviewer decides what to do with what this
        surfaces, the same way readiness issues are shown but not force-
        fixed automatically."""
        report = self.get_object()
        return Response({"issues": validate_report_data(report)})

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        # NOT "?format=" — that's DRF's own reserved query param for
        # content-negotiation/renderer selection (URL_FORMAT_OVERRIDE);
        # using it here made DRF's content negotiation raise Http404
        # before this method's body ever ran, since no renderer declares
        # format="csv"/"xlsx"/"pdf"/"xml".
        report = self.get_object()
        fmt = request.query_params.get("export_format", "csv")
        filename = f"{report.form_type}_{report.report_year}_v{report.version}"
        if fmt == "csv":
            return HttpResponse(
                export.to_csv(report), content_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
            )
        if fmt == "xlsx":
            return HttpResponse(
                export.to_excel(report), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
            )
        if fmt == "pdf":
            return HttpResponse(
                export.to_pdf(report), content_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
            )
        if fmt == "xml":
            return HttpResponse(
                export.to_xml(report), content_type="application/xml",
                headers={"Content-Disposition": f'attachment; filename="{filename}.xml"'},
            )
        raise ValidationError({"detail": "export_format must be one of csv, xlsx, pdf, xml."})


# --- C6: consultation forum + plan depth (design spec 2026-08-26) --------


class EEForumMemberViewSet(viewsets.ModelViewSet):
    """EEForumPermission lets any authenticated employee GET; the queryset
    narrows to the requester's own seat(s) for non-EE roles (spec §5: a
    member may see who they sit with — the list is the meeting-attendee
    roster — but a non-member sees nothing). Writes are role-gated in the
    permission class."""

    queryset = EEForumMember.objects.select_related("employee")
    serializer_class = EEForumMemberSerializer
    permission_classes = [EEForumPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if not is_ee_reader(employee):
            # Members see the whole roster (they sit on it together);
            # everyone else sees nothing.
            if not EEForumMember.objects.filter(employee=employee).exists():
                return qs.none()
        if self.request.query_params.get("active") == "1":
            today = timezone.localdate()
            qs = qs.filter(term_start__lte=today).filter(Q(term_end__isnull=True) | Q(term_end__gte=today))
        return qs

    @action(detail=False, methods=["get"])
    def composition(self, request):
        """Derived s.16(2) adequacy check — EE read roles only (it
        summarises the whole workforce's level/designated-group mix)."""
        if not is_ee_reader(get_request_employee(request)):
            raise PermissionDenied("Only EE reporting roles can view the forum composition check.")
        return Response(forum_composition())


class EEForumMeetingViewSet(viewsets.ModelViewSet):
    queryset = EEForumMeeting.objects.select_related("recorded_by").prefetch_related("attendees")
    serializer_class = EEForumMeetingSerializer
    permission_classes = [EEForumPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = super().get_queryset()
        employee = get_request_employee(self.request)
        if not is_ee_reader(employee):
            qs = qs.filter(attendees__employee=employee).distinct()
        report_year = int_query_param(self.request, "report_year")
        if report_year is not None:
            qs = qs.filter(report_year=report_year)
        return qs

    def _validate_minutes(self, serializer):
        uploaded = serializer.validated_data.get("minutes_file")
        if uploaded is None:
            return {}
        try:
            content_type, sha256 = validate_minutes_upload(uploaded)
        except MinutesValidationError as exc:
            raise ValidationError({"minutes_file": str(exc)})
        return {"minutes_content_type": content_type, "minutes_sha256": sha256}

    def perform_create(self, serializer):
        serializer.save(recorded_by=get_request_employee(self.request), **self._validate_minutes(serializer))

    def perform_update(self, serializer):
        serializer.save(**self._validate_minutes(serializer))

    @action(detail=True, methods=["get"])
    def download_minutes(self, request, pk=None):
        """Authenticated FileResponse — same shape as policies/performance
        evidence; `get_object()` applies the attendee carve-out, so a member
        can only pull minutes of meetings they attended."""
        meeting = self.get_object()
        if not meeting.minutes_file:
            return Response({"detail": "This meeting has no uploaded minutes."}, status=404)
        log_access(
            actor=get_request_employee(request), action=AuditLogEntry.Action.EXPORT,
            entity_type="ee_reporting.EEForumMeeting", entity_id=meeting.pk, field_tier=FieldTier.SENSITIVE,
            fields_touched=f"downloaded minutes of {meeting.meeting_date} meeting",
        )
        filename = os.path.basename(meeting.minutes_file.name)
        return FileResponse(meeting.minutes_file.open("rb"), as_attachment=True, filename=filename)


class EEPlanMeasureViewSet(viewsets.ModelViewSet):
    queryset = EEPlanMeasure.objects.select_related("owner", "plan")
    serializer_class = EEPlanMeasureSerializer
    permission_classes = [EEOperationalPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        plan_id = int_query_param(self.request, "plan")
        if plan_id is not None:
            qs = qs.filter(plan_id=plan_id)
        for param in ("category", "status"):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{param: value})
        return qs


class EEPlanProgressSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """Create-only via `take/` (matrices are always server-computed); no
    update/delete — a snapshot is evidence of what was tabled."""

    queryset = EEPlanProgressSnapshot.objects.select_related("plan", "taken_by")
    serializer_class = EEPlanProgressSnapshotSerializer
    permission_classes = [EEOperationalPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        plan_id = int_query_param(self.request, "plan")
        if plan_id is not None:
            qs = qs.filter(plan_id=plan_id)
        return qs

    def _suppressed(self, data: dict) -> dict:
        employee = get_request_employee(self.request)
        suppress = not can_see_unsuppressed_aggregates(employee, FieldTier.SENSITIVE)
        data["small_cell_suppression_applied"] = suppress
        for key in ("workforce_profile", "disability_workforce"):
            data[key] = _suppress_matrix(data[key], suppress=suppress)
        return data

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        items = [self._suppressed(d) for d in self.get_serializer(page, many=True).data]
        return self.get_paginated_response(items)

    def retrieve(self, request, *args, **kwargs):
        return Response(self._suppressed(self.get_serializer(self.get_object()).data))

    @action(detail=False, methods=["post"])
    def take(self, request):
        input_serializer = TakeSnapshotSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            snapshot = take_progress_snapshot(actor=get_request_employee(request), **input_serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self._suppressed(self.get_serializer(snapshot).data), status=201)
