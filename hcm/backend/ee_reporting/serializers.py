from __future__ import annotations

from core_hr.models import Employee
from rest_framework import serializers

from .models import EEPlan, EEQuestionnaire, EEReport, EmployerConfig, RemunerationRecord


class EmployerConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployerConfig
        fields = "__all__"


class EEPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = EEPlan
        fields = [
            "id", "plan_period_start", "plan_period_end", "sector_targets", "numerical_goals",
            "disability_5yr_target_pct", "annual_targets", "annual_target_disability_value",
            "annual_target_disability_pct", "created_by",
        ]
        read_only_fields = ["created_by"]


class EEQuestionnaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = EEQuestionnaire
        fields = [
            "id", "report_year", "achieved_all_targets", "justifiable_reasons", "consultation", "barriers",
            "monitoring_frequency", "achieved_annual_objectives", "achieved_annual_objectives_explanation",
            "has_remuneration_policy", "remuneration_gap_aligned_to_policy", "has_measures_in_ee_plan",
            "differential_reason", "differential_reason_other", "vertical_gap_multiple", "updated_by",
        ]
        read_only_fields = ["updated_by"]


class RemunerationRecordSerializer(serializers.ModelSerializer):
    total_remuneration = serializers.IntegerField(read_only=True)
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)

    class Meta:
        model = RemunerationRecord
        fields = [
            "id", "employee", "employee_number", "period_start", "period_end",
            "fixed_remuneration", "variable_remuneration", "total_remuneration", "imported_by",
        ]
        read_only_fields = ["imported_by"]


class EEReportSerializer(serializers.ModelSerializer):
    """Read-only end to end — `data` is always server-computed by
    services.py::generate_report, never client-writable, and every other
    field changes only through the dedicated review/sign-off actions."""

    class Meta:
        model = EEReport
        fields = [
            "id", "form_type", "report_year", "version", "period_start", "period_end", "status", "data",
            "generated_by", "generated_at", "ee_reviewed_by", "ee_reviewed_at",
            "signed_off_by", "signed_off_at", "signed_off_place",
        ]
        read_only_fields = fields


class GenerateReportSerializer(serializers.Serializer):
    form_type = serializers.ChoiceField(choices=EEReport.FormType.choices)
    report_year = serializers.IntegerField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()


class SignOffSerializer(serializers.Serializer):
    place = serializers.CharField(required=False, allow_blank=True, default="")
