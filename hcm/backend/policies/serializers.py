from __future__ import annotations

from rest_framework import serializers

from .models import Policy, PolicyAcknowledgment, PolicyChunk


class PolicySerializer(serializers.ModelSerializer):
    # Not required — a policy is created either from typed `body` or an
    # uploaded `source_file` (see services.py::create_policy/update_draft);
    # when both are sent, the file wins and overwrites `body` server-side.
    source_file = serializers.FileField(required=False, allow_null=True)
    chunk_count = serializers.IntegerField(source="chunks.count", read_only=True)

    class Meta:
        model = Policy
        fields = [
            "id", "code", "title", "category", "body", "source_file", "chunk_count", "version", "status",
            "effective_date", "created_by", "published_by", "published_at",
        ]
        # code/version/status are server-computed (services.py) — never
        # client-set directly; publishing/versioning go through the
        # dedicated publish/new_version actions, not a raw PATCH.
        read_only_fields = ["code", "version", "status", "created_by", "published_by", "published_at"]


class PolicyChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyChunk
        fields = ["id", "sequence", "text"]


class PolicyAcknowledgmentSerializer(serializers.ModelSerializer):
    policy_title = serializers.CharField(source="policy.title", read_only=True)
    policy_version = serializers.IntegerField(source="policy.version", read_only=True)
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)

    class Meta:
        model = PolicyAcknowledgment
        fields = ["id", "employee", "employee_number", "policy", "policy_title", "policy_version", "acknowledged_at"]
        # employee is never client-set — an acknowledgment is always
        # self-recorded, even for hr_admin (see the model docstring).
        read_only_fields = ["employee", "acknowledged_at"]
