from __future__ import annotations

from rbac_audit.drf import get_request_employee
from rbac_audit.permissions import has_role
from rest_framework import serializers

from .models import AssessmentAssignment, AssessmentResult, ProviderConfig


class AssessmentResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentResult
        fields = ["raw_score", "summary", "detail", "received_at"]


class AssessmentAssignmentSerializer(serializers.ModelSerializer):
    """Plain ModelSerializer, not TieredModelSerializer — see
    permissions.py::CanAccessAssessmentAssignment for why: access is
    gated at the object level (whole-row visibility), not per-field,
    matching performance.Review's precedent. employee/applicant_id/
    assessment_type are the only client-writable fields — everything else
    is computed server-side by services.py::assign_assessment (adapter
    call result) or process_webhook_result (status/completion)."""

    result = AssessmentResultSerializer(read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentAssignment
        fields = [
            "id", "employee", "employee_name", "applicant_id", "assessment_type", "provider_key", "provider_reference",
            "access_url", "status", "assigned_by", "completed_at", "result", "created_at",
        ]
        read_only_fields = [
            "provider_key", "provider_reference", "access_url", "status", "assigned_by", "completed_at",
        ]

    def get_employee_name(self, obj) -> str | None:
        if obj.employee is None:
            return None
        return f"{obj.employee.preferred_name or obj.employee.first_name} {obj.employee.last_name}".strip()

    def validate(self, attrs):
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        employee = attrs.get("employee")
        applicant_id = attrs.get("applicant_id")

        if (employee is None) == (applicant_id is None):
            raise serializers.ValidationError("Exactly one of employee or applicant_id must be set.")
        if employee is not None and not (has_role(requester, "hr_admin") or has_role(requester, "ee_manager")):
            raise serializers.ValidationError("Only hr_admin or ee_manager can assign assessments to employees.")
        if applicant_id is not None and not (has_role(requester, "hr_admin") or has_role(requester, "recruiter")):
            raise serializers.ValidationError("Only hr_admin or recruiter can assign assessments to applicants.")
        return attrs


class ProviderConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderConfig
        fields = ["id", "provider_key", "display_name", "active", "config"]
