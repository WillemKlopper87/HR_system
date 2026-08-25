"""Serializers for calibration/moderation (C6). No update/delete route for
`CalibrationAdjustment` at all -- it's only ever created through
`CalibrationSessionViewSet.record_outcome`, never via a ModelViewSet of its
own (services/calibration.py::record_calibration_outcome is the only writer).
`CalibrationSession.status` is read-only here too; it only moves via the
`close` action, so a raw PATCH can't skip `close_session`'s audit log entry.
"""
from __future__ import annotations

from rest_framework import serializers

from .models.calibration import CalibrationAdjustment, CalibrationSession


class CalibrationAdjustmentSerializer(serializers.ModelSerializer):
    adjusted_by_name = serializers.SerializerMethodField()
    agreement_employee_name = serializers.SerializerMethodField()

    class Meta:
        model = CalibrationAdjustment
        fields = [
            "id", "session", "agreement", "agreement_employee_name", "previous_score", "new_score", "reason",
            "adjusted_by", "adjusted_by_name", "created_at",
        ]
        read_only_fields = fields  # create-only, through the session action

    def get_adjusted_by_name(self, obj) -> str | None:
        return f"{obj.adjusted_by.first_name} {obj.adjusted_by.last_name}" if obj.adjusted_by_id else None

    def get_agreement_employee_name(self, obj) -> str:
        return f"{obj.agreement.employee.first_name} {obj.agreement.employee.last_name}"


class CalibrationSessionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    period_name = serializers.CharField(source="period.name", read_only=True)
    convened_by_name = serializers.SerializerMethodField()
    adjustments = CalibrationAdjustmentSerializer(many=True, read_only=True)

    class Meta:
        model = CalibrationSession
        fields = [
            "id", "period", "period_name", "department", "department_name", "status", "status_display",
            "meeting_date", "participants_note", "summary", "convened_by", "convened_by_name", "completed_at",
            "created_at", "adjustments",
        ]
        read_only_fields = ["status", "convened_by", "completed_at", "created_at"]

    def get_convened_by_name(self, obj) -> str | None:
        return f"{obj.convened_by.first_name} {obj.convened_by.last_name}" if obj.convened_by_id else None

    def validate(self, attrs):
        if self.instance is not None and self.instance.status == CalibrationSession.Status.COMPLETED:
            raise serializers.ValidationError("This calibration session is completed and can no longer be edited.")
        return attrs


class RecordOutcomeSerializer(serializers.Serializer):
    agreement = serializers.IntegerField()
    reason = serializers.CharField()
    new_score = serializers.DecimalField(max_digits=4, decimal_places=2, required=False, allow_null=True)


class CalibrationCandidateSerializer(serializers.Serializer):
    """Minimal read shape for "who's eligible in this cohort and not yet
    recorded" -- the list a session's `candidates` action returns."""

    id = serializers.IntegerField()
    employee_name = serializers.SerializerMethodField()
    employee_number = serializers.CharField(source="employee.employee_number")
    department_name = serializers.SerializerMethodField()
    final_score = serializers.CharField()
    hr_attention = serializers.BooleanField()

    def get_employee_name(self, obj) -> str:
        return f"{obj.employee.first_name} {obj.employee.last_name}"

    def get_department_name(self, obj) -> str | None:
        version = obj.employee.current_version
        return version.department.name if version and version.department_id else None
