from __future__ import annotations

from rbac_audit.audit import log_access
from rbac_audit.consent import has_active_consent
from rbac_audit.drf import get_request_employee
from rbac_audit.models import AuditLogEntry, ConsentRecord
from rbac_audit.permissions import can_access_tier, has_role
from rbac_audit.tiers import FieldTier, highest_tier, tier_of
from rest_framework import serializers

from .models import (
    Applicant,
    ApplicantStageEvent,
    BackgroundCheck,
    InterviewScorecard,
    InterviewSession,
    Offer,
    Requisition,
)
from .services import validate_requisition_positions
from .validation import ResumeValidationError, sniff_resume_content_type, validate_resume_upload

DEMOGRAPHIC_FIELDS = {"race", "gender", "disability_status"}


class RequisitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Requisition
        fields = [
            "id", "title", "department", "occupational_level", "job_grade", "location",
            "headcount", "status", "hiring_manager", "created_by", "positions",
            "opened_at", "target_fill_date", "closed_at", "description", "external_posting",
        ]
        # status is directly writable (draft/open/on_hold/closed) — the
        # view auto-stamps opened_at/closed_at as a side effect. Simpler
        # than Applicant's dedicated transition action since Requisition
        # status has no equivalent ALLOWED_TRANSITIONS validation to enforce.
        read_only_fields = ["created_by", "closed_at"]

    def validate(self, attrs):
        # `positions` missing from the payload means this write isn't
        # touching the link at all (the only requisition-mutation UI is a
        # status-only PATCH). Requisitions that predate establishment
        # control -- and the seeded demo ones -- have zero linked
        # positions; enforcing "at least one" on every write would lock
        # them out of ever changing status again. So the non-empty rule
        # applies only when `positions` is actually being written, or on
        # create (where a requisition must always name its posts).
        positions_supplied = "positions" in attrs
        positions = list(attrs["positions"]) if positions_supplied else list(
            self.instance.positions.all() if self.instance else []
        )
        if not positions and (positions_supplied or self.instance is None):
            raise serializers.ValidationError(
                {"positions": "At least one approved, vacant position is required."}
            )
        if not positions:
            # Grandfathered: nothing to validate, and the checks below all
            # assume a non-empty list.
            return attrs
        headcount = attrs.get("headcount", self.instance.headcount if self.instance else 1)
        # Where this requisition is actually hiring, as of THIS write --
        # from the payload if it's being set/changed, otherwise the stored
        # value. Passed explicitly because on create there is no instance
        # for validate_requisition_positions to read them off.
        department = attrs.get("department", self.instance.department if self.instance else None)
        location = attrs.get("location", self.instance.location if self.instance else None)
        try:
            validate_requisition_positions(
                positions,
                headcount=headcount,
                requisition=self.instance,
                requisition_department_id=department.pk if department is not None else None,
                requisition_location_id=location.pk if location is not None else None,
            )
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
            "has_demographic_consent", "resulting_employee", "source", "resume",
            "resume_content_type", "resume_size_bytes",
        ]
        # source is set only by the create path (recruiter-entered defaults
        # to "internal"; the careers portal's own submit_portal_application
        # sets "portal" directly, bypassing this serializer entirely) — never
        # writable through this endpoint, so a recruiter can't relabel a
        # portal-sourced applicant's provenance after the fact.
        # resume_content_type/resume_size_bytes are server-derived (see
        # validate_resume/create/update below) — never client-supplied.
        read_only_fields = [
            "current_stage", "rejected_reason", "resulting_employee", "source",
            "resume_content_type", "resume_size_bytes",
        ]

    def validate_resume(self, value):
        """A recruiter can attach a CV to an internally-sourced applicant
        too (design spec §2.5) — same content-sniffing discipline as the
        careers portal's own submission path, not a portal-only check."""
        if value:
            try:
                validate_resume_upload(value)
            except ResumeValidationError as exc:
                raise serializers.ValidationError(str(exc)) from exc
        return value

    @staticmethod
    def _derive_resume_fields(validated_data):
        resume = validated_data.get("resume")
        if resume:
            validated_data["resume_content_type"] = sniff_resume_content_type(resume)
            validated_data["resume_size_bytes"] = resume.size

    def create(self, validated_data):
        self._derive_resume_fields(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        self._derive_resume_fields(validated_data)
        return super().update(instance, validated_data)

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


# --- C6: interview scheduling, panel scorecards, background checks --------

class InterviewApplicantSummarySerializer(serializers.ModelSerializer):
    """Design spec §3.1: deliberately narrow, and — unlike ApplicantSerializer
    above — the SAME shape for every caller including recruiter/hr_admin. No
    demographics, no email/phone/date_of_birth, no rejected_reason, no prior
    stage-event notes. This is what an assigned interviewer (who may hold no
    recruitment-module role at all) is allowed to know about the applicant
    they're interviewing."""

    requisition_title = serializers.CharField(source="requisition.title", read_only=True)

    class Meta:
        model = Applicant
        fields = ["id", "first_name", "last_name", "requisition", "requisition_title", "current_stage", "resume"]
        read_only_fields = fields


class InterviewSessionSerializer(serializers.ModelSerializer):
    applicant_summary = InterviewApplicantSummarySerializer(source="applicant", read_only=True)

    class Meta:
        model = InterviewSession
        fields = [
            "id", "applicant", "applicant_summary", "round_number", "scheduled_at", "duration_minutes",
            "location", "status", "notes", "interviewers", "created_by", "created_at",
        ]
        read_only_fields = ["created_by"]

    def validate(self, attrs):
        applicant = attrs.get("applicant", self.instance.applicant if self.instance else None)
        if applicant is not None and applicant.current_stage != Applicant.Stage.INTERVIEW:
            raise serializers.ValidationError(
                {"applicant": "Interviews can only be scheduled for an applicant at the 'interview' stage."}
            )
        interviewers = attrs.get("interviewers")
        if interviewers is not None and len(interviewers) == 0:
            raise serializers.ValidationError({"interviewers": "At least one interviewer is required."})
        return attrs


class InterviewScorecardSerializer(serializers.ModelSerializer):
    """Design spec §2.2, §3.2: `interviewer` is force-set server-side (see
    create() below) to whoever is authenticated — never client-supplied, so
    nobody can submit "on behalf of" someone else. Blind-review masking
    (peer scorecards hidden until the viewer has submitted their own for the
    same session) lives in to_representation, not in the permission class —
    the permission class only decides whether the ROW is reachable at all."""

    class Meta:
        model = InterviewScorecard
        fields = [
            "id", "session", "interviewer", "skill_rating", "communication_rating",
            "culture_fit_rating", "comments", "recommendation", "created_at",
        ]
        read_only_fields = ["interviewer"]

    def validate(self, attrs):
        session = attrs.get("session", self.instance.session if self.instance else None)
        request = self.context.get("request")
        employee = get_request_employee(request) if request is not None else None
        if session is None or employee is None:
            return attrs
        if not session.interviewers.filter(pk=employee.pk).exists():
            raise serializers.ValidationError(
                {"session": "You are not an assigned interviewer for this session."}
            )
        duplicate = InterviewScorecard.objects.filter(session=session, interviewer=employee)
        if self.instance is not None:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError("You have already submitted a scorecard for this session.")
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["interviewer"] = get_request_employee(request) if request is not None else None
        return super().create(validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        viewer = get_request_employee(request) if request is not None else None
        if viewer is None:
            return data
        if has_role(viewer, "recruiter") or has_role(viewer, "hr_admin"):
            return data
        if viewer.id == instance.interviewer_id:
            return data
        has_submitted_own = InterviewScorecard.objects.filter(
            session_id=instance.session_id, interviewer=viewer
        ).exists()
        if has_submitted_own:
            return data
        # Blind until the viewer has committed their own scorecard for this
        # session (design spec §2.2) — the row's existence is still visible
        # (id/session/interviewer/created_at), just not its content.
        for field in ("skill_rating", "communication_rating", "culture_fit_rating", "comments", "recommendation"):
            data.pop(field, None)
        return data


class BackgroundCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackgroundCheck
        fields = [
            "id", "applicant", "check_type", "status", "requested_by", "requested_at",
            "completed_at", "notes", "created_at",
        ]
        read_only_fields = ["requested_by"]
