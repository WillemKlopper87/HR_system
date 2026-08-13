from __future__ import annotations

from rbac_audit.drf import TieredModelSerializer, get_request_employee
from rbac_audit.permissions import has_row_access
from rest_framework import serializers

from .models import Certification, EmployeeSkill, Skill, TrainingRecord


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ["id", "name", "category", "description", "active"]


class RowScopedLearningSerializer(TieredModelSerializer):
    """Shared validate() for EmployeeSkill/Certification/TrainingRecord:
    self, your manager (own_team), or hr_admin can create/edit an entry
    for a given employee — same row-scope check as performance.Goal
    (Sprint 6). Internal-tier fields have no line_manager-blocking
    conflict (unlike performance.Review's Sensitive-tier ones), so this
    safely uses the standard tiered path."""

    def validate(self, attrs):
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        target = attrs.get("employee") or getattr(self.instance, "employee", None)
        if target is not None and not has_row_access(requester, target):
            raise serializers.ValidationError("You don't have access to manage learning records for this employee.")
        return attrs


class EmployeeSkillSerializer(RowScopedLearningSerializer):
    class Meta:
        model = EmployeeSkill
        fields = ["id", "employee", "skill", "proficiency", "acquired_date", "notes"]


class CertificationSerializer(RowScopedLearningSerializer):
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Certification
        fields = ["id", "employee", "name", "issuing_body", "credential_id", "issue_date", "expiry_date", "is_expired"]


class TrainingRecordSerializer(RowScopedLearningSerializer):
    class Meta:
        model = TrainingRecord
        fields = ["id", "employee", "title", "provider", "status", "start_date", "completion_date", "hours", "cost"]
