from rbac_audit.consent import has_active_consent
from rbac_audit.drf import TieredModelSerializer, get_request_employee
from rbac_audit.models import ConsentRecord
from rbac_audit.permissions import has_role, is_in_reporting_chain
from rest_framework import serializers

from .models import (
    ContractRenewalDecision,
    DataQualityException,
    Department,
    Employee,
    EmployeeVersion,
    JobGrade,
    Location,
    OccupationalLevel,
)

# Sprint 15 (ESS): the only fields a PATCH through EmployeeViewSet may
# touch, for self or hr_admin alike — RBAC-Roles.md's employee row: "*W on
# ESS-editable fields only (contact details, self-ID via consent flow)".
# Demographic self-ID is a separate, consent-gated action
# (EmployeeViewSet.self_identify), not a plain field PATCH.
ESS_EDITABLE_FIELDS = {"preferred_name", "personal_email", "phone"}


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
