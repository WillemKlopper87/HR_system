from rbac_audit.consent import has_active_consent
from rbac_audit.drf import TieredModelSerializer, get_request_employee
from rbac_audit.models import ConsentRecord
from rbac_audit.permissions import has_role, is_in_reporting_chain
from rest_framework import serializers

from .models import (
    ContractRenewalDecision,
    DataQualityException,
    Dependant,
    Department,
    Employee,
    EmergencyContact,
    EmployeeVersion,
    EmploymentChange,
    JobGrade,
    Location,
    OccupationalLevel,
)
from .permissions import is_self_or_hr_admin

# Sprint 15 (ESS): the only fields a PATCH through EmployeeViewSet may
# touch, for self or hr_admin alike — RBAC-Roles.md's employee row: "*W on
# ESS-editable fields only (contact details, self-ID via consent flow)".
# Demographic self-ID is a separate, consent-gated action
# (EmployeeViewSet.self_identify), not a plain field PATCH.
ESS_EDITABLE_FIELDS = {"preferred_name", "personal_email", "phone"}


class ContractActionInputSerializer(serializers.Serializer):
    """Request-body validation for EmployeeVersionViewSet.recommend_contract
    /decide_contract. Both actions used to read request.data directly and
    hand `end_date` straight to the ORM, where DateField.get_prep_value()
    raises django.core.exceptions.ValidationError -- an Exception, not a
    ValueError, so neither contracts.py's `except ValueError` nor DRF's
    default exception handler (settings.py sets no EXCEPTION_HANDLER)
    caught it: an unparseable date was an unhandled 500. Same defect class
    rbac_audit.drf.int_query_param already hardened the read layer
    against; is_valid(raise_exception=True) gives the write layer the
    equivalent clean 400 with per-field errors.

    This also subsumes the hand-rolled `action not in Action.values`
    check both view methods used to carry -- one validation path, not two.
    Ordering ("the new end_date must be after the version's current
    contract_end_date", spec §4) deliberately stays in core_hr/contracts.py:
    it is a domain-state rule about the target version, not a shape rule
    about the payload, and belongs with every other ContractDecisionError
    per that module's docstring."""

    action = serializers.ChoiceField(choices=ContractRenewalDecision.Action.choices)
    end_date = serializers.DateField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class ContractRenewalDecisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractRenewalDecision
        fields = [
            "id", "status",
            "recommended_action", "recommended_by", "recommended_at", "recommended_comment", "recommended_end_date",
            "decided_action", "decided_by", "decided_at", "decided_comment", "decided_end_date",
            "resulting_employee_version",
        ]


class EmployeeVersionSerializer(TieredModelSerializer):
    contract_renewal_decision = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeVersion
        fields = [
            "id", "employee", "valid_from", "valid_to", "department", "job_title",
            "occupational_level", "job_grade", "manager", "employment_status",
            "citizenship_status", "location", "contract_end_date", "contract_renewal_decision",
            "race", "gender", "disability_status", "disability_detail", "race_source", "disability_source",
        ]

    def get_contract_renewal_decision(self, obj):
        try:
            decision = obj.contract_renewal_decision
        except ContractRenewalDecision.DoesNotExist:
            return None
        # Design spec Sec2, explicitly out of scope: "the employee does not
        # see or participate in this workflow -- only the outcome (their
        # employment record changing) is visible to them" (contract_end_date
        # stays visible -- that IS the outcome; PUBLIC-tier, untouched by
        # this check). This is a row-relational gate, not a field-tier one:
        # the base "employee" role's self row-scope grants I:read on the
        # subject's own row same as everyone else's, so tiering alone (see
        # rbac_audit/tiers.py's INTERNAL registration above) can't exclude
        # just the subject -- checked here instead. Someone who is ALSO the
        # subject's line manager, hr_admin, or auditor (design spec Sec6's
        # three intended-consumer roles) still sees it via that separate
        # entitlement, the same way they would for anyone else's record --
        # only a bare subject-with-no-other-entitlement is hidden from it.
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        subject = obj.employee
        if requester is not None and requester.id == subject.id:
            has_separate_entitlement = (
                has_role(requester, "hr_admin")
                or has_role(requester, "auditor")
                or (has_role(requester, "line_manager") and is_in_reporting_chain(requester, subject))
            )
            if not has_separate_entitlement:
                return None
        return ContractRenewalDecisionSerializer(decision).data


class EmployeeSerializer(TieredModelSerializer):
    """Identity fields only (Data-Dictionary.md core_hr.Employee) — current
    department/job title/status come from EmployeeVersion (?current=true),
    kept as a separate fetch rather than duplicated here so tiering logic
    for time-varying attributes stays in one place (EmployeeVersionSerializer)."""

    # Same shape as recruitment.ApplicantSerializer.has_demographic_consent
    # — PUBLIC-tier (unregistered in FIELD_TIERS, defaults there), always
    # shown, so the ESS self-ID UI knows whether to show "capture consent"
    # or the self-ID form without a separate lookup.
    has_demographic_consent = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id", "employee_number", "first_name", "last_name", "preferred_name",
            "national_id_number", "passport_number", "date_of_birth", "work_email",
            "personal_email", "phone", "hire_date", "has_demographic_consent",
        ]

    def get_has_demographic_consent(self, instance) -> bool:
        return instance.pk is not None and has_active_consent(
            employee=instance, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID
        )

    def validate(self, attrs):
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        target = self.instance
        if target is not None:
            is_self = requester is not None and requester.id == target.id
            is_hr_admin = requester is not None and has_role(requester, "hr_admin")
            if not (is_self or is_hr_admin):
                raise serializers.ValidationError("You don't have access to update this employee's profile.")
            if attrs.keys() - ESS_EDITABLE_FIELDS:
                raise serializers.ValidationError(
                    f"Only these fields can be updated here: {', '.join(sorted(ESS_EDITABLE_FIELDS))}."
                )
        return attrs


class _SelfOrHRAdminSerializer(TieredModelSerializer):
    """Shared validate() for Dependant/EmergencyContact (C2 design spec
    §2.8): narrower than learning.RowScopedLearningSerializer's
    has_row_access -- self or hr_admin only, never a line_manager's
    own_team scope, since managing a report's dependants/emergency
    contacts is HR administration, not team management."""

    def validate(self, attrs):
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        target = attrs.get("employee") or getattr(self.instance, "employee", None)
        if target is not None and not is_self_or_hr_admin(requester, target):
            raise serializers.ValidationError("You don't have access to manage this employee's records.")
        return attrs


class DependantSerializer(_SelfOrHRAdminSerializer):
    class Meta:
        model = Dependant
        fields = ["id", "employee", "first_name", "last_name", "relationship", "date_of_birth", "id_number", "notes"]


class EmergencyContactSerializer(_SelfOrHRAdminSerializer):
    class Meta:
        model = EmergencyContact
        fields = [
            "id", "employee", "name", "relationship", "phone", "alternative_phone", "email", "is_primary",
        ]


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "code", "parent", "active"]


class OccupationalLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = OccupationalLevel
        fields = ["id", "name", "code", "order", "active"]


class JobGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobGrade
        fields = ["id", "name", "code", "occupational_level", "active"]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "code", "province", "active"]


class EmploymentChangeSerializer(serializers.ModelSerializer):
    """employee/change_type/effective_date/reason are the only
    client-writable fields on create ('propose' — see
    EmploymentChangeViewSet.perform_create) — state, the proposer/
    confirmer/canceller trail, and the lift's link back to the suspension
    it restores are all computed server-side by exits.py's service layer,
    never trusted from client input (same shape as
    compensation.CompProposalSerializer). effective_date is genuinely
    client-writable for every OTHER change type, but for
    DISMISSAL_SUMMARY the service layer overwrites whatever is submitted
    with today's date regardless (spec §4.2) — nothing to enforce here,
    that rule lives in exits.py alongside the rest of the state machine."""

    class Meta:
        model = EmploymentChange
        fields = [
            "id", "employee", "change_type", "state", "effective_date", "reason",
            "proposed_by", "proposed_at", "confirmed_by", "confirmed_at", "executed_at",
            "cancelled_by", "cancelled_at", "cancellation_reason",
            "lifts_suspension", "resulting_event",
        ]
        read_only_fields = [
            "state", "proposed_by", "proposed_at", "confirmed_by", "confirmed_at", "executed_at",
            "cancelled_by", "cancelled_at", "cancellation_reason",
            "lifts_suspension", "resulting_event",
        ]


class DataQualityExceptionSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = DataQualityException
        fields = [
            "id", "employee", "employee_number", "employee_name",
            "exception_type", "detail", "detected_at", "resolved_at",
        ]
        read_only_fields = ["employee", "exception_type", "detail", "detected_at"]

    def get_employee_name(self, obj) -> str:
        return f"{obj.employee.first_name} {obj.employee.last_name}"
