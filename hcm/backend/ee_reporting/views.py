from __future__ import annotations

from django.http import HttpResponse
from rbac_audit.drf import get_request_employee, int_query_param
from rbac_audit.permissions import has_role
from rbac_audit.stepup import RequiresPayrollStepUp
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from . import export
from .models import EEPlan, EEQuestionnaire, EEReport, EmployerConfig, RemunerationRecord
from .permissions import EEReportingPermission
from .serializers import (
    EEPlanSerializer,
    EEQuestionnaireSerializer,
    EEReportSerializer,
    EmployerConfigSerializer,
    GenerateReportSerializer,
    RemunerationRecordSerializer,
    SignOffSerializer,
)
from .services import (
    ApprovalError,
    RemunerationImportError,
    ReportNotReadyError,
    ee_manager_approve,
    generate_report,
    import_remuneration_csv,
    sign_off,
    submit_for_review,
)


def _require_hr_admin(actor, message):
    """EEReportingPermission's has_permission is deliberately coarse
    (any of hr_admin/ee_manager/accounting_officer may reach a POST, so
    ee_review/sign_off's OWN role checks below aren't blocked upstream —
    see permissions.py). Actions that really are hr_admin-only (config/
    plan/questionnaire writes, generate, submit, CSV import) enforce that
    narrower rule here instead."""
    if not has_role(actor, "hr_admin"):
        raise PermissionDenied(message)


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
    permission_classes = [EEReportingPermission, RequiresPayrollStepUp]
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
