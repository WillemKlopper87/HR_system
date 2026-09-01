from __future__ import annotations

from core_hr.models import Employee
from rest_framework import serializers

from .models import BiometricEnrollment, LivenessCheck


class BiometricConsentStatusSerializer(serializers.Serializer):
    active = serializers.BooleanField(read_only=True)


class BiometricConsentSerializer(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    lawful_basis = serializers.ChoiceField(choices=["consent"], default="consent")
    text_version = serializers.CharField(max_length=50, default="biometric-v1")


class BiometricEnrollmentSerializer(serializers.ModelSerializer):
    """Deliberately never exposes `descriptor` — the client writes a new
    one (via the create input serializer below) but has no reason to read
    its own stored template back; this is purely an enrollment-status
    view."""

    class Meta:
        model = BiometricEnrollment
        fields = ["id", "employee", "enrolled_by", "created_at", "updated_at"]
        read_only_fields = fields


class BiometricEnrollmentCreateSerializer(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    descriptor = serializers.ListField(child=serializers.FloatField(), min_length=128, max_length=128)


class LivenessCheckSerializer(serializers.ModelSerializer):
    employee_display = serializers.SerializerMethodField()

    class Meta:
        model = LivenessCheck
        fields = [
            "id", "employee", "employee_display", "trigger", "requested_by", "match_distance", "outcome",
            "latitude", "longitude", "distance_from_office_m", "at_office",
            "review_status", "reviewed_by", "reviewed_at", "review_notes", "created_at",
        ]
        read_only_fields = [
            "match_distance", "outcome", "distance_from_office_m", "at_office",
            "review_status", "reviewed_by", "reviewed_at", "review_notes",
        ]

    def get_employee_display(self, obj) -> str:
        return f"{obj.employee.employee_number} — {obj.employee.first_name} {obj.employee.last_name}"


class LivenessCheckCreateSerializer(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    descriptor = serializers.ListField(
        child=serializers.FloatField(), min_length=128, max_length=128, required=False, allow_null=True
    )
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)


class ReviewDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[LivenessCheck.ReviewStatus.CONFIRMED_MATCH, LivenessCheck.ReviewStatus.CONFIRMED_MISMATCH]
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
