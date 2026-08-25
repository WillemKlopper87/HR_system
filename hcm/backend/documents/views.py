from __future__ import annotations

import os

from django.http import FileResponse
from rbac_audit.consent import record_consent
from rbac_audit.drf import get_request_employee, int_query_param
from rbac_audit.models import ConsentRecord
from rbac_audit.permissions import can_access_tier_for_target, has_role
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core_hr.models import Employee
from core_hr.permissions import is_self_or_hr_admin

from .models import DataSubjectRequest, EmployeeDocument
from .permissions import DataSubjectRequestPermission, EmployeeDocumentPermission
from .serializers import DataSubjectRequestSerializer, EmployeeDocumentSerializer
from .services import (
    DocumentError,
    complete_erasure_request,
    complete_export_request,
    decline_data_subject_request,
    delete_employee_document,
    submit_data_subject_request,
    upload_employee_document,
)


class EmployeeDocumentViewSet(viewsets.ModelViewSet):
    """No PATCH of `file`/`document_type` — a re-upload is a new document,
    not an edit of an existing one (design spec §9: "no versioning", a
    deliberate simplification vs. policies.Policy). Only `title`/
    `description` are patchable through the plain serializer path."""

    queryset = EmployeeDocument.objects.select_related("employee", "uploaded_by")
    serializer_class = EmployeeDocumentSerializer
    permission_classes = [EmployeeDocumentPermission]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        target_id = int_query_param(self.request, "employee")
        if target_id is not None:
            queryset = queryset.filter(employee_id=target_id)
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        if employee is None:
            return queryset.none()
        # Design spec §5.1: row-tier gated, two-pass at demo scale (same
        # "fine at the hundreds-of-rows scale" caveat fetchAllPages already
        # documents) — can_access_tier_for_target needs the SPECIFIC
        # covering role per row, which a blanket queryset filter can't
        # express (see rbac_audit.permissions.can_access_tier_for_target's
        # own docstring on why a blanket check would leak).
        allowed_ids = [
            doc.id for doc in queryset
            if can_access_tier_for_target(employee, doc.employee, doc.tier, mode="read")
        ]
        return queryset.filter(id__in=allowed_ids)

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        employee = serializer.validated_data["employee"]
        if not is_self_or_hr_admin(actor, employee):
            raise ValidationError({"detail": "You don't have access to upload a document for this employee."})
        try:
            serializer.instance = upload_employee_document(
                employee,
                document_type=serializer.validated_data["document_type"],
                title=serializer.validated_data["title"],
                description=serializer.validated_data.get("description", ""),
                file=serializer.validated_data["file"],
                actor=actor,
            )
        except DocumentError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    def perform_destroy(self, instance):
        delete_employee_document(instance, actor=get_request_employee(self.request))

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Authenticated download — reuses policies.PolicyViewSet.download's
        exact pattern (design spec §5.1): self.get_object() already ran
        EmployeeDocumentPermission's row-tier object check, so this is not
        a raw MEDIA_URL link (config/urls.py mounts none)."""
        document = self.get_object()
        filename = os.path.basename(document.file.name)
        return FileResponse(document.file.open("rb"), as_attachment=True, filename=filename)

    @action(detail=False, methods=["post"])
    def consent(self, request):
        """Same shape as identity_verification.LivenessCheckViewSet.consent
        — self or hr_admin captures EMPLOYEE_DOCUMENTS-purpose consent
        before an id_copy/disability_verification upload can succeed
        (design spec §2.7)."""
        employee_id = request.data.get("employee")
        if not employee_id:
            return Response({"detail": "employee is required."}, status=400)
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return Response({"detail": "No such employee."}, status=400)
        actor = get_request_employee(request)
        if not is_self_or_hr_admin(actor, employee):
            return Response({"detail": "Only the employee themself or hr_admin can capture this consent."}, status=403)
        record_consent(
            employee=employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS,
            lawful_basis=request.data.get("lawful_basis", ConsentRecord.LawfulBasis.CONSENT),
            text_version=request.data.get("text_version", "v1"), actor=actor,
        )
        return Response({"detail": "Consent recorded."}, status=201)


class DataSubjectRequestViewSet(viewsets.ModelViewSet):
    """No DELETE — a request is actioned (completed/declined), not
    withdrawn from the record (design spec §5.3)."""

    queryset = DataSubjectRequest.objects.select_related("employee", "requested_by", "reviewed_by")
    serializer_class = DataSubjectRequestSerializer
    permission_classes = [DataSubjectRequestPermission]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action != "list":
            return queryset
        employee = get_request_employee(self.request)
        if employee is None:
            return queryset.none()
        if has_role(employee, "hr_admin") or has_role(employee, "auditor"):
            return queryset
        return queryset.filter(employee=employee)

    def perform_create(self, serializer):
        actor = get_request_employee(self.request)
        employee = serializer.validated_data["employee"]
        if not is_self_or_hr_admin(actor, employee):
            raise ValidationError({"detail": "You don't have access to file a request for this employee."})
        try:
            serializer.instance = submit_data_subject_request(
                employee,
                request_type=serializer.validated_data["request_type"],
                notes=serializer.validated_data.get("request_notes", ""),
                actor=actor,
            )
        except DocumentError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        data_subject_request = self.get_object()
        actor = get_request_employee(request)
        if not has_role(actor, "hr_admin"):
            return Response({"detail": "Only hr_admin can action a data-subject request."}, status=403)
        notes = request.data.get("resolution_notes", "")
        try:
            if data_subject_request.request_type == DataSubjectRequest.RequestType.EXPORT:
                complete_export_request(data_subject_request, actor=actor, notes=notes)
            else:
                complete_erasure_request(data_subject_request, actor=actor, notes=notes)
        except DocumentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(data_subject_request).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        data_subject_request = self.get_object()
        actor = get_request_employee(request)
        if not has_role(actor, "hr_admin"):
            return Response({"detail": "Only hr_admin can action a data-subject request."}, status=403)
        try:
            decline_data_subject_request(data_subject_request, actor=actor, notes=request.data.get("resolution_notes", ""))
        except DocumentError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(data_subject_request).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """The completed EXPORT artifact — same authenticated FileResponse
        pattern as policies.PolicyViewSet.download and
        EmployeeDocumentViewSet.download above."""
        data_subject_request = self.get_object()
        if not data_subject_request.export_file:
            return Response({"detail": "No export file is available for this request."}, status=404)
        filename = os.path.basename(data_subject_request.export_file.name)
        return FileResponse(data_subject_request.export_file.open("rb"), as_attachment=True, filename=filename)
