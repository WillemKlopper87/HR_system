# hcm/backend/establishment/serializers.py
from __future__ import annotations

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

    class Meta:
        model = Position
        fields = [
            "id", "post_number", "title", "department", "occupational_level", "job_grade", "location",
            "status", "current_step", "proposed_by", "approval_steps", "is_vacant", "current_incumbent_number",
        ]
        read_only_fields = ["post_number", "status", "current_step", "proposed_by"]

    def get_current_incumbent_number(self, obj) -> str | None:
        occupant = obj.current_occupant
        return occupant.employee.employee_number if occupant else None
