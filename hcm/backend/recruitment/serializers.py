from __future__ import annotations

from rbac_audit.audit import log_access
from rbac_audit.consent import has_active_consent
from rbac_audit.drf import get_request_employee
from rbac_audit.models import AuditLogEntry, ConsentRecord
from rbac_audit.permissions import can_access_tier
from rbac_audit.tiers import FieldTier, highest_tier, tier_of
from rest_framework import serializers

from .models import Applicant, ApplicantStageEvent, Offer, Requisition
from .services import validate_requisition_positions

DEMOGRAPHIC_FIELDS = {"race", "gender", "disability_status"}


class RequisitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Requisition
        fields = [
            "id", "title", "department", "occupational_level", "job_grade", "location",
            "headcount", "status", "hiring_manager", "created_by", "positions",
            "opened_at", "target_fill_date", "closed_at",
        ]
        # status is directly writable (draft/open/on_hold/closed) — the
        # view auto-stamps opened_at/closed_at as a side effect. Simpler
        # than Applicant's dedicated transition action since Requisition
        # status has no equivalent ALLOWED_TRANSITIONS validation to enforce.
        read_only_fields = ["created_by", "closed_at"]

    def validate(self, attrs):
        positions = attrs.get("positions")
        if positions is None:
            positions = list(self.instance.positions.all()) if self.instance else []
        headcount = attrs.get("headcount", self.instance.headcount if self.instance else 1)
        if not positions:
            raise serializers.ValidationError(
                {"positions": "At least one approved, vacant position is required."}
            )
        try:
            validate_requisition_positions(list(positions), headcount=headcount, requisition=self.instance)
        except ValueError as exc:
            raise serializers.ValidationError({"positions": str(exc)})
        return attrs


class ApplicantSerializer(serializers.ModelSerializer):
    """Row-scope for Applicant is trivially "all" — only recruiter/hr_admin
    reach this endpoint (IsRecruiterOrHRAdmin) — so this composes rbac_audit's
    primitives directly rather than subclassing TieredModelSerializer, which
    is built around a specific target_employee and row-scope reasoning that
    doesn't apply here. Demographic fields carry an ADDITIONAL consent gate
    on top of the tier grant (Data-Dictionary.md: "applicant (S — demographics,
    consent-gated)") — both must hold, tier grant alone isn't sufficient."""

    # Whether consent exists is PUBLIC-tier and always shown — it's not
    # itself sensitive information, and the UI needs an unambiguous signal
    # distinct from "are the tier grant AND consent both satisfied for me,
    # right now" (which is all that race/gender/disability_status's
    # presence/absence in the response actually tells you).
    has_demographic_consent = serializers.SerializerMethodField()

    class Meta:
        model = Applicant
        fields = [
            "id", "requisition", "first_name", "last_name", "email", "phone", "date_of_birth",
            "current_stage", "rejected_reason", "race", "gender", "disability_status",
            "has_demographic_consent", "resulting_employee",
        ]
        read_only_fields = ["current_stage", "rejected_reason", "resulting_employee"]

    def get_has_demographic_consent(self, instance) -> bool:
        return instance.pk is not None and has_active_consent(
            applicant=instance, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID
        )

    def validate(self, attrs):
        if DEMOGRAPHIC_FIELDS & attrs.keys():
            if self.instance is None or not has_active_consent(
                applicant=self.instance, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID
            ):
                raise serializers.ValidationError(
                    "Demographic fields require active consent — "
                    "POST /api/v1/applicants/{id}/consent/ first."
                )
        return attrs

    def to_representation(self, instance):
        request = self.context.get("request")
        employee = get_request_employee(request) if request is not None else None
        model_label = "recruitment.Applicant"

        data = super().to_representation(instance)
        # get_has_demographic_consent already computed this for the
        # has_demographic_consent field above — reuse it instead of
        # querying has_active_consent a second time.
        has_consent = bool(data.get("has_demographic_consent"))
        allowed_fields = []
        for name in data:
            tier = tier_of(model_label, name)
            if tier == FieldTier.PUBLIC:
                allowed_fields.append(name)
            elif name in DEMOGRAPHIC_FIELDS and not has_consent:
                continue
            elif can_access_tier(employee, tier, mode="read"):
                allowed_fields.append(name)
        filtered = {name: data[name] for name in allowed_fields}

        touched_tier = highest_tier(model_label, allowed_fields)
        if touched_tier != FieldTier.PUBLIC:
            log_access(
                actor=employee,
                action=AuditLogEntry.Action.READ_SENSITIVE,
                entity_type=model_label,
                entity_id=instance.pk,
                field_tier=touched_tier,
                fields_touched=",".join(allowed_fields),
            )
        return filtered


class ApplicantStageEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicantStageEvent
        fields = ["id", "applicant", "from_stage", "to_stage", "changed_by", "notes", "created_at"]


class OfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = [
            "id", "applicant", "proposed_job_grade", "proposed_annual_salary", "status",
            "proposed_by", "approved_by", "approved_at", "start_date",
        ]
        read_only_fields = ["status", "proposed_by", "approved_by", "approved_at"]
