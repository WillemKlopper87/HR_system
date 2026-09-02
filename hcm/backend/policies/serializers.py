from __future__ import annotations

from rest_framework import serializers

from .models import Policy, PolicyAcknowledgment, PolicyApproval, PolicyChunk


class PolicyApprovalSerializer(serializers.ModelSerializer):
    approved_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PolicyApproval
        fields = ["id", "approved_by", "approved_by_name", "comment", "approved_at"]
        read_only_fields = ["approved_by", "approved_at"]

    def get_approved_by_name(self, obj) -> str:
        return f"{obj.approved_by.first_name} {obj.approved_by.last_name}"


class PolicySerializer(serializers.ModelSerializer):
    # Not required — a policy is created either from typed `body` or an
    # uploaded `source_file` (see services.py::create_policy/update_draft);
    # when both are sent, the file wins and overwrites `body` server-side.
    # write_only: the raw MEDIA_URL this would otherwise serialize to is an
    # unauthenticated static file link (django.views.static.serve has no
    # permission/RBAC layer at all) — reads go through `download_url`
    # instead, which points at PolicyViewSet.download, gated by the same
    # IsHRAdminOrReadOnly + status-filtered queryset as everything else.
    source_file = serializers.FileField(required=False, allow_null=True, write_only=True)
    has_source_file = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    chunk_count = serializers.IntegerField(source="chunks.count", read_only=True)
    approvals = PolicyApprovalSerializer(many=True, read_only=True)
    pending_committee_approvals = serializers.SerializerMethodField()

    class Meta:
        model = Policy
        fields = [
            "id", "code", "title", "category", "body", "source_file", "has_source_file", "download_url",
            "chunk_count", "version", "status", "effective_date", "created_by", "published_by", "published_at",
            "approvals", "pending_committee_approvals",
        ]
        # code/version/status are server-computed (services.py) — never
        # client-set directly; publishing/versioning go through the
        # dedicated publish/new_version actions, not a raw PATCH.
        read_only_fields = ["code", "version", "status", "created_by", "published_by", "published_at"]

    def get_has_source_file(self, obj) -> bool:
        return bool(obj.source_file)

    def get_download_url(self, obj) -> str | None:
        if not obj.source_file:
            return None
        request = self.context.get("request")
        path = f"/api/v1/policies/{obj.pk}/download/"
        return request.build_absolute_uri(path) if request is not None else path

    def get_pending_committee_approvals(self, obj) -> list[str]:
        """Names of every committee member who hasn't approved this draft
        yet — empty once published/archived, since a settled policy has
        nothing left pending. Committee membership is cached on `context`
        (shared across every row in a `many=True` list serialization) so
        listing N drafts costs one committee query, not N."""
        if obj.status != Policy.Status.DRAFT:
            return []
        if "committee_members" not in self.context:
            from .services import current_committee_members

            self.context["committee_members"] = list(current_committee_members())
        approved_ids = {a.approved_by_id for a in obj.approvals.all()}
        return [
            f"{e.first_name} {e.last_name}" for e in self.context["committee_members"] if e.id not in approved_ids
        ]


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
