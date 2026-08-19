# hcm/backend/establishment/serializers.py
from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from .models import Position, PositionApprovalStep


class PositionApprovalStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = PositionApprovalStep
        fields = ["id", "step_index", "role", "actor", "decision", "comment", "created_at"]


class PositionSerializer(serializers.ModelSerializer):
    approval_steps = PositionApprovalStepSerializer(many=True, read_only=True)
    is_vacant = serializers.BooleanField(read_only=True)
    current_incumbent_number = serializers.SerializerMethodField()
    next_approver_role = serializers.SerializerMethodField()

    class Meta:
        model = Position
        fields = [
            "id", "post_number", "title", "department", "occupational_level", "job_grade", "location",
            "status", "current_step", "proposed_by", "approval_steps", "is_vacant", "current_incumbent_number",
            "next_approver_role",
        ]
        read_only_fields = ["post_number", "status", "current_step", "proposed_by"]

    def get_current_incumbent_number(self, obj) -> str | None:
        occupant = obj.current_occupant
        return occupant.employee.employee_number if occupant else None

    def get_next_approver_role(self, obj) -> str | None:
        """The role that must act next, mirroring views.PositionViewSet.
        decide()'s own chain lookup -- the frontend reads this instead of
        re-deriving it from a hardcoded copy of POSITION_APPROVAL_CHAIN,
        which is deployment-configurable (settings.py)."""
        if obj.status != Position.Status.IN_REVIEW:
            return None
        chain = settings.POSITION_APPROVAL_CHAIN
        if obj.current_step >= len(chain):
            return None
        return chain[obj.current_step]
