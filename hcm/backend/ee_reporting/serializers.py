from __future__ import annotations

from core_hr.models import Employee
from rest_framework import serializers

from .models import (
    EEForumMeeting,
    EEForumMember,
    EEPlan,
    EEPlanMeasure,
    EEPlanProgressSnapshot,
    EEQuestionnaire,
    EEReport,
    EmployerConfig,
    RemunerationRecord,
)
from .permissions import is_ee_reader


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
            "annual_target_disability_pct", "eap_profile", "created_by",
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


# --- C6: consultation forum + plan depth (design spec 2026-08-26) --------


def _employee_name(employee) -> str:
    return f"{employee.first_name} {employee.last_name}".strip()


class EEForumMemberSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = EEForumMember
        fields = [
            "id", "employee", "employee_number", "employee_name", "representation", "role",
            "term_start", "term_end", "notes", "is_active",
        ]

    def get_employee_name(self, obj) -> str:
        return _employee_name(obj.employee)

    def get_is_active(self, obj) -> bool:
        from django.utils import timezone

        return obj.is_active_on(timezone.localdate())

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # `representation` can reveal trade-union membership — POPIA s.26
        # special personal information, gated like race/disability (spec
        # §5): a reader who only reaches this through the member carve-out
        # (not an EE role) gets the seat, not the nomination basis.
        request = self.context.get("request")
        if request is not None:
            from rbac_audit.drf import get_request_employee

            if not is_ee_reader(get_request_employee(request)):
                data.pop("representation", None)
                data.pop("notes", None)
        return data

    def validate(self, attrs):
        term_start = attrs.get("term_start", getattr(self.instance, "term_start", None))
        term_end = attrs.get("term_end", getattr(self.instance, "term_end", None))
        if term_end is not None and term_start is not None and term_end < term_start:
            raise serializers.ValidationError({"term_end": "term_end must be on or after term_start."})
        employee = attrs.get("employee", getattr(self.instance, "employee", None))
        overlapping = EEForumMember.objects.filter(employee=employee)
        if self.instance is not None:
            overlapping = overlapping.exclude(pk=self.instance.pk)
        for other in overlapping:
            starts_before_other_ends = other.term_end is None or term_start <= other.term_end
            ends_after_other_starts = term_end is None or term_end >= other.term_start
            if starts_before_other_ends and ends_after_other_starts:
                raise serializers.ValidationError(
                    {"term_start": f"{employee.employee_number} already holds a seat overlapping this term."}
                )
        return attrs


class EEForumMeetingSerializer(serializers.ModelSerializer):
    attendee_count = serializers.SerializerMethodField()
    has_minutes = serializers.SerializerMethodField()
    minutes_download_url = serializers.SerializerMethodField()
    minutes_file = serializers.FileField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = EEForumMeeting
        fields = [
            "id", "meeting_date", "title", "report_year", "agenda", "summary", "resolutions", "attendees",
            "attendee_count", "minutes_file", "has_minutes", "minutes_content_type", "minutes_sha256",
            "minutes_download_url", "recorded_by",
        ]
        read_only_fields = ["minutes_content_type", "minutes_sha256", "recorded_by"]

    def get_attendee_count(self, obj) -> int:
        return len(obj.attendees.all())

    def get_has_minutes(self, obj) -> bool:
        return bool(obj.minutes_file)

    def get_minutes_download_url(self, obj) -> str | None:
        return f"/api/v1/ee-forum-meetings/{obj.pk}/download_minutes/" if obj.minutes_file else None


class EEPlanMeasureSerializer(serializers.ModelSerializer):
    owner_number = serializers.CharField(source="owner.employee_number", read_only=True)
    owner_name = serializers.SerializerMethodField()
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = EEPlanMeasure
        fields = [
            "id", "plan", "category", "category_label", "barrier_description", "measure_description",
            "owner", "owner_number", "owner_name", "target_start", "target_end", "status", "progress_notes",
            "is_overdue",
        ]

    def get_owner_name(self, obj) -> str:
        return _employee_name(obj.owner)

    def validate(self, attrs):
        plan = attrs.get("plan", getattr(self.instance, "plan", None))
        start = attrs.get("target_start", getattr(self.instance, "target_start", None))
        end = attrs.get("target_end", getattr(self.instance, "target_end", None))
        if start and end and end < start:
            raise serializers.ValidationError({"target_end": "target_end must be on or after target_start."})
        # EEA13: the time frame sits inside the plan period.
        if plan and start and end and not (plan.plan_period_start <= start and end <= plan.plan_period_end):
            raise serializers.ValidationError(
                {"target_end": f"The measure's time frame must fall within the plan period {plan.plan_period_start}–{plan.plan_period_end}."}
            )
        return attrs


class EEPlanProgressSnapshotSerializer(serializers.ModelSerializer):
    """Read shape. Matrices are suppressed per requester in the view (never
    here — the serializer doesn't know who's asking without a request)."""

    class Meta:
        model = EEPlanProgressSnapshot
        fields = [
            "id", "plan", "as_of", "workforce_profile", "disability_workforce", "annual_target_gap_pct",
            "sector_target_gap_pct", "eap_gap_pct", "designated_group_pct", "disability_pct", "flags", "note",
            "taken_by", "created_at",
        ]
        read_only_fields = fields


class TakeSnapshotSerializer(serializers.Serializer):
    plan = serializers.PrimaryKeyRelatedField(queryset=EEPlan.objects.all())
    as_of = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=300)
