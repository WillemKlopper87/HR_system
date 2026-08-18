"""Serializers for the performance-agreement domain (PC-1, ADR-010).

Plain ModelSerializers, not `TieredModelSerializer` — the same exception the
`Review` model documents: row scope plus `permissions.py` is the real gate
here, and a scorecard is meaningless with half its fields stripped.

Write access is narrowed in `validate()` rather than by field-level tiering:
only content fields move through the API, and every *state* change goes
through a named action backed by `services/agreements.py`, so no PATCH can
skip the workflow (same shape as `ee_reporting.EEReport`).
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    AgreementDocument,
    AgreementElement,
    AgreementSignature,
    AgreementTemplate,
    PDPItem,
    PerformanceAgreement,
    PerformancePeriod,
    PeriodPhase,
    SigningDelegation,
    TemplateElement,
    TemplateSection,
)


class PeriodPhaseSerializer(serializers.ModelSerializer):
    stage_display = serializers.CharField(source="get_stage_display", read_only=True)

    class Meta:
        model = PeriodPhase
        fields = ["id", "period", "stage", "stage_display", "opens_on", "due_on",
                  "reminder_offsets_days", "overdue_every_days"]


class PerformancePeriodSerializer(serializers.ModelSerializer):
    phases = PeriodPhaseSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    agreement_count = serializers.SerializerMethodField()

    class Meta:
        model = PerformancePeriod
        fields = ["id", "name", "start_date", "end_date", "status", "status_display", "phases",
                  "attention_threshold", "agreement_count", "created_by"]
        read_only_fields = ["status", "created_by"]

    def get_agreement_count(self, obj) -> int:
        return obj.agreements.count()


class TemplateElementSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateElement
        fields = ["id", "template", "section", "kpa_description", "kpi_title", "metric",
                  "default_weight", "level_descriptors", "order", "locked"]


class TemplateSectionSerializer(serializers.ModelSerializer):
    elements = TemplateElementSerializer(many=True, read_only=True)

    class Meta:
        model = TemplateSection
        fields = ["id", "template", "title", "order", "locked", "elements"]


class AgreementTemplateSerializer(serializers.ModelSerializer):
    sections = TemplateSectionSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    total_default_weight = serializers.SerializerMethodField()

    class Meta:
        model = AgreementTemplate
        fields = ["id", "name", "version", "status", "status_display", "period", "rating_scale",
                  "evidence_required", "signature_method", "job_grades", "occupational_levels",
                  "departments", "sections", "total_default_weight", "published_at", "created_by"]
        read_only_fields = ["status", "published_at", "created_by"]

    def get_total_default_weight(self, obj) -> str:
        return str(sum((e.default_weight for e in obj.elements.all()), Decimal("0")))


class AgreementElementSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()

    class Meta:
        model = AgreementElement
        fields = ["id", "agreement", "section_title", "section_order", "kpa_description", "kpi_title",
                  "metric", "weight", "level_descriptors", "order", "locked",
                  "q2_target_note", "q2_employee_comment", "q2_head_comment",
                  "final_rating", "final_employee_comment", "final_head_comment", "score"]
        read_only_fields = ["agreement"]

    def get_score(self, obj) -> str | None:
        score = obj.score
        return None if score is None else str(score)

    def validate(self, attrs):
        agreement = self.instance.agreement if self.instance else None
        if agreement is not None and not agreement.is_editable:
            # Ratings/comments (PC-2) will have their own stage rules; contracting
            # content is frozen the moment the agreement leaves draft/returned.
            frozen = {"kpa_description", "kpi_title", "metric", "weight", "level_descriptors", "order"}
            if frozen & set(attrs):
                raise serializers.ValidationError(
                    "This agreement is no longer in draft — amend it (with a reason) to change the scorecard."
                )
        if self.instance and self.instance.locked:
            if {"kpi_title", "weight", "kpa_description"} & set(attrs):
                raise serializers.ValidationError(
                    "This KPI is cascaded from the corporate scorecard and cannot be edited."
                )
        weight = attrs.get("weight")
        if weight is not None and (weight < 0 or weight > 1):
            raise serializers.ValidationError({"weight": "Weight is a fraction between 0 and 1 (e.g. 0.20 for 20%)."})
        return attrs


class PDPItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PDPItem
        fields = ["id", "agreement", "business_process", "course_or_training", "order", "training_record_id"]


class AgreementSignatureSerializer(serializers.ModelSerializer):
    signer_name = serializers.SerializerMethodField()
    acting_for_name = serializers.SerializerMethodField()
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    method_display = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = AgreementSignature
        fields = ["id", "agreement", "stage", "revision", "role", "role_display", "signer", "signer_name",
                  "acting_for", "acting_for_name", "signed_at", "method", "method_display",
                  "document", "document_sha256"]

    def get_signer_name(self, obj) -> str:
        return f"{obj.signer.first_name} {obj.signer.last_name}"

    def get_acting_for_name(self, obj) -> str | None:
        return f"{obj.acting_for.first_name} {obj.acting_for.last_name}" if obj.acting_for_id else None


class AgreementDocumentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = AgreementDocument
        fields = ["id", "agreement", "stage", "revision", "sha256", "generated_at", "download_url"]

    def get_download_url(self, obj) -> str:
        return f"/api/v1/performance-agreements/{obj.agreement_id}/documents/{obj.id}/download/"


class PerformanceAgreementSerializer(serializers.ModelSerializer):
    elements = AgreementElementSerializer(many=True, read_only=True)
    pdp_items = PDPItemSerializer(many=True, read_only=True)
    signatures = AgreementSignatureSerializer(many=True, read_only=True)
    documents = AgreementDocumentSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    employee_name = serializers.SerializerMethodField()
    head_name = serializers.SerializerMethodField()
    period_name = serializers.CharField(source="period.name", read_only=True)
    total_weight = serializers.SerializerMethodField()
    current_stage = serializers.CharField(read_only=True)
    is_editable = serializers.BooleanField(read_only=True)

    class Meta:
        model = PerformanceAgreement
        fields = ["id", "period", "period_name", "employee", "employee_name", "head", "head_name",
                  "template", "template_version", "revision", "status", "status_display",
                  "return_reason", "amendment_reason", "final_score", "hr_attention", "hr_attention_reason",
                  "submitted_at", "agreed_at", "total_weight", "current_stage", "is_editable",
                  "elements", "pdp_items", "signatures", "documents"]
        read_only_fields = fields  # every mutation goes through a named action

    def get_employee_name(self, obj) -> str:
        return f"{obj.employee.first_name} {obj.employee.last_name}"

    def get_head_name(self, obj) -> str | None:
        return f"{obj.head.first_name} {obj.head.last_name}" if obj.head_id else None

    def get_total_weight(self, obj) -> str:
        return str(obj.total_weight)


class SigningDelegationSerializer(serializers.ModelSerializer):
    delegator_name = serializers.SerializerMethodField()
    delegate_name = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = SigningDelegation
        fields = ["id", "delegator", "delegator_name", "delegate", "delegate_name", "start_date", "end_date",
                  "reason", "created_by", "revoked_at", "is_active"]
        read_only_fields = ["created_by", "revoked_at"]

    def get_delegator_name(self, obj) -> str:
        return f"{obj.delegator.first_name} {obj.delegator.last_name}"

    def get_delegate_name(self, obj) -> str:
        return f"{obj.delegate.first_name} {obj.delegate.last_name}"

    def get_is_active(self, obj) -> bool:
        from django.utils import timezone

        return obj.is_active_on(timezone.localdate())

    def validate(self, attrs):
        start = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "The delegation must end on or after it starts."})
        delegator = attrs.get("delegator") or getattr(self.instance, "delegator", None)
        delegate = attrs.get("delegate") or getattr(self.instance, "delegate", None)
        if delegator and delegate and delegator.pk == delegate.pk:
            raise serializers.ValidationError({"delegate": "A Head cannot delegate signing to themselves."})
        return attrs


class SignRequestSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=AgreementSignature.Role.choices)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True, style={"input_type": "password"})


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)
