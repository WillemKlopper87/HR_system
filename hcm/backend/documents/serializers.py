from __future__ import annotations

from rest_framework import serializers

from .models import DataSubjectRequest, EmployeeDocument


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    # write_only, same reasoning as policies.PolicySerializer.source_file —
    # the raw MEDIA_URL this would otherwise serialize to is an
    # unauthenticated static file link (config/urls.py deliberately mounts
    # no MEDIA_URL static() route); reads go through `download_url`
    # instead, gated by the same EmployeeDocumentPermission-filtered
    # queryset as everything else (documents/views.py::download).
    file = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()
    tier = serializers.CharField(read_only=True)
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    uploaded_by_number = serializers.CharField(source="uploaded_by.employee_number", read_only=True, default=None)

    class Meta:
        model = EmployeeDocument
        fields = [
            "id", "employee", "employee_number", "document_type", "title", "description", "file",
            "download_url", "content_type", "size_bytes", "tier", "uploaded_by", "uploaded_by_number", "created_at",
        ]
        read_only_fields = ["content_type", "size_bytes", "uploaded_by", "created_at"]

    def get_download_url(self, obj) -> str:
        request = self.context.get("request")
        path = f"/api/v1/employee-documents/{obj.pk}/download/"
        return request.build_absolute_uri(path) if request is not None else path


class DataSubjectRequestSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    requested_by_number = serializers.CharField(source="requested_by.employee_number", read_only=True, default=None)
    reviewed_by_number = serializers.CharField(source="reviewed_by.employee_number", read_only=True, default=None)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = DataSubjectRequest
        fields = [
            "id", "employee", "employee_number", "request_type", "status",
            "requested_by", "requested_by_number", "requested_at", "request_notes",
            "reviewed_by", "reviewed_by_number", "reviewed_at", "resolution_notes", "download_url",
        ]
        # Server-computed throughout (services.py) — never a raw PATCH; see
        # documents/views.py's complete/decline actions.
        read_only_fields = [
            "status", "requested_by", "requested_at", "reviewed_by", "reviewed_at", "resolution_notes",
        ]

    def get_download_url(self, obj) -> str | None:
        if not obj.export_file:
            return None
        request = self.context.get("request")
        path = f"/api/v1/data-subject-requests/{obj.pk}/download/"
        return request.build_absolute_uri(path) if request is not None else path
