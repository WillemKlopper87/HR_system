"""Serializers for 360 feedback (C6). The visibility/anonymity split (design
spec §2.10) lives entirely in `Feedback360RaterSerializer.get_response` --
full attributed detail to the Head/hr_admin/auditor and to a rater's own row,
full attributed detail to the *subject* for self/manager relationships only,
and nothing at all (not masked fields, the whole nested object is omitted)
for peer/direct_report rows viewed by the subject -- the aggregate on
`Feedback360RequestSerializer` carries that signal instead, ratings-only,
gated on the ≥3-response floor.
"""
from __future__ import annotations

from rest_framework import serializers

from rbac_audit.drf import get_request_employee

from .models.feedback360 import Feedback360Rater, Feedback360Request, Feedback360Response
from .permissions import can_read_all, is_head_of
from .services.feedback360 import aggregate_for


class Feedback360ResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback360Response
        fields = [
            "id", "rater_slot", "collaboration_rating", "communication_rating", "reliability_rating",
            "strengths", "development_areas", "submitted_at",
        ]
        read_only_fields = ["rater_slot", "submitted_at"]


class Feedback360RaterSerializer(serializers.ModelSerializer):
    rater_name = serializers.SerializerMethodField()
    relationship_display = serializers.CharField(source="get_relationship_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    has_submitted = serializers.SerializerMethodField()
    response = serializers.SerializerMethodField()
    # Convenience context for "/my-feedback-requests" (design spec §7),
    # where a bare `request` id isn't enough to show the rater who they're
    # being asked to rate -- mirrors the *_name convenience fields used
    # throughout this module rather than making the frontend fetch the
    # parent Feedback360Request/agreement separately.
    subject_name = serializers.SerializerMethodField()
    period_name = serializers.CharField(source="request.agreement.period.name", read_only=True)

    class Meta:
        model = Feedback360Rater
        fields = [
            "id", "request", "rater", "rater_name", "relationship", "relationship_display", "status",
            "status_display", "nominated_by", "approved_by", "approved_at", "has_submitted", "response",
            "subject_name", "period_name", "created_at",
        ]
        read_only_fields = ["relationship", "status", "nominated_by", "approved_by", "approved_at", "created_at"]

    def get_rater_name(self, obj) -> str:
        return f"{obj.rater.first_name} {obj.rater.last_name}"

    def get_subject_name(self, obj) -> str:
        employee = obj.request.agreement.employee
        return f"{employee.first_name} {employee.last_name}"

    def get_has_submitted(self, obj) -> bool:
        return obj.has_submitted

    def get_response(self, obj):
        response = getattr(obj, "response", None)
        if response is None:
            return None
        request_ctx = self.context.get("request")
        viewer = get_request_employee(request_ctx) if request_ctx is not None else None
        if viewer is None:
            return None
        agreement = obj.request.agreement
        # Full attributed detail: Head/delegate, hr_admin, auditor, or the
        # rater's own submitted response.
        if can_read_all(viewer) or is_head_of(agreement, viewer) or viewer.pk == obj.rater_id:
            return Feedback360ResponseSerializer(response).data
        # The subject sees a self/manager response in full (no new exposure
        # vs. final_head_comment, already visible to them elsewhere) but
        # never an individual peer/direct_report row -- permanently, not
        # just pre-submission (spec §2.10). The aggregate field carries that
        # signal instead.
        if viewer.pk == agreement.employee_id and obj.relationship in (
            Feedback360Rater.Relationship.SELF, Feedback360Rater.Relationship.MANAGER,
        ):
            return Feedback360ResponseSerializer(response).data
        return None


class Feedback360RequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    opened_by_name = serializers.SerializerMethodField()
    raters = Feedback360RaterSerializer(many=True, read_only=True)
    peer_aggregate = serializers.SerializerMethodField()
    direct_report_aggregate = serializers.SerializerMethodField()

    class Meta:
        model = Feedback360Request
        fields = [
            "id", "agreement", "status", "status_display", "opened_by", "opened_by_name", "due_date",
            "closed_at", "created_at", "raters", "peer_aggregate", "direct_report_aggregate",
        ]
        read_only_fields = ["status", "opened_by", "closed_at", "created_at"]

    def get_opened_by_name(self, obj) -> str | None:
        return f"{obj.opened_by.first_name} {obj.opened_by.last_name}" if obj.opened_by_id else None

    def get_peer_aggregate(self, obj):
        return aggregate_for(obj, Feedback360Rater.Relationship.PEER)

    def get_direct_report_aggregate(self, obj):
        return aggregate_for(obj, Feedback360Rater.Relationship.DIRECT_REPORT)


class SubmitResponseSerializer(serializers.Serializer):
    collaboration_rating = serializers.IntegerField(min_value=1, max_value=5)
    communication_rating = serializers.IntegerField(min_value=1, max_value=5)
    reliability_rating = serializers.IntegerField(min_value=1, max_value=5)
    strengths = serializers.CharField(required=False, allow_blank=True, default="")
    development_areas = serializers.CharField(required=False, allow_blank=True, default="")
