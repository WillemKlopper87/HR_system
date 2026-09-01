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
    ExitInterview,
    OccupationalLevel,
    ProbationPeriod,
    ProbationReview,
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


class ProbationReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProbationReview
        fields = [
            "id", "probation_period", "review_date", "reviewed_by", "recommendation", "comments",
            "employee_signed_at", "employee_signature_sha256",
        ]
        read_only_fields = ["reviewed_by", "employee_signed_at", "employee_signature_sha256"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        period = attrs.get("probation_period") or getattr(self.instance, "probation_period", None)
        review_date = attrs.get("review_date") or getattr(self.instance, "review_date", None)
        if period is not None and review_date is not None:
            if review_date < period.start_date or review_date > period.end_date:
                raise serializers.ValidationError(
                    {"review_date": f"Must fall within the probation window ({period.start_date} to {period.end_date})."}
                )
        return attrs


class ProbationPeriodSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    reviews = ProbationReviewSerializer(many=True, read_only=True)

    class Meta:
        model = ProbationPeriod
        fields = [
            "id", "employee", "employee_number", "start_date", "end_date", "status",
            "outcome_at", "outcome_by", "outcome_notes", "reviews",
        ]
        read_only_fields = ["status", "outcome_at", "outcome_by"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start_date = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end_date = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": "Must be on or after the start date."})

        if self.instance is None:
            employee = attrs.get("employee")
            overlapping = ProbationPeriod.objects.filter(
                employee=employee,
                status__in=[ProbationPeriod.Status.IN_PROGRESS, ProbationPeriod.Status.EXTENDED],
            ).exists()
            if overlapping:
                raise serializers.ValidationError(
                    "This employee already has an open probation period -- close it before opening another."
                )
        return attrs


class ExitInterviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExitInterview
        fields = [
            "id", "employee", "employment_change", "probation_period", "interview_date", "conducted_by",
            "primary_reason", "would_recommend_employer", "comments",
        ]
        read_only_fields = ["conducted_by"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        employee = attrs.get("employee") or getattr(self.instance, "employee", None)
        employment_change = attrs.get("employment_change") if "employment_change" in attrs else getattr(
            self.instance, "employment_change", None
        )
        probation_period = attrs.get("probation_period") if "probation_period" in attrs else getattr(
            self.instance, "probation_period", None
        )
        if employment_change is not None and employment_change.employee_id != employee.id:
            raise serializers.ValidationError(
                {"employment_change": "Must belong to the selected employee."}
            )
        if probation_period is not None and probation_period.employee_id != employee.id:
            raise serializers.ValidationError(
                {"probation_period": "Must belong to the selected employee."}
            )
        if employment_change is not None and probation_period is not None:
            raise serializers.ValidationError(
                "An exit interview links to at most one of employment_change or probation_period, not both --"
                " a genuine exit and a probation non-confirmation are distinct triggers."
            )
        return attrs


class EmployeeVersionSerializer(TieredModelSerializer):
    contract_renewal_decision = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeVersion
        fields = [
            "id", "employee", "employee_name", "valid_from", "valid_to", "department", "job_title",
            "occupational_level", "job_grade", "manager", "manager_name", "employment_status",
            "citizenship_status", "location", "contract_end_date", "contract_renewal_decision",
            "race", "gender", "disability_status", "disability_detail", "race_source", "disability_source",
        ]

    @staticmethod
    def _display_name(employee) -> str | None:
        if employee is None:
            return None
        return f"{employee.preferred_name or employee.first_name} {employee.last_name}".strip()

    def get_employee_name(self, obj) -> str:
        return self._display_name(obj.employee) or ""

    def get_manager_name(self, obj) -> str | None:
        return self._display_name(obj.manager)

    def get_contract_renewal_decision(self, obj) -> dict | None:
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
    current_department = serializers.SerializerMethodField()
    current_occupational_level = serializers.SerializerMethodField()
    current_employment_status = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id", "employee_number", "first_name", "last_name", "preferred_name",
            "national_id_number", "passport_number", "date_of_birth", "work_email",
            "personal_email", "phone", "hire_date", "has_demographic_consent",
            "current_department", "current_occupational_level", "current_employment_status",
        ]

    def get_has_demographic_consent(self, instance) -> bool:
        return instance.pk is not None and has_active_consent(
            employee=instance, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID
        )

    @staticmethod
    def _current_version(instance):
        prefetched = getattr(instance, "current_versions_for_summary", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return instance.current_version

    def get_current_department(self, instance) -> int | None:
        version = self._current_version(instance)
        return version.department_id if version else None

    def get_current_occupational_level(self, instance) -> int | None:
        version = self._current_version(instance)
        return version.occupational_level_id if version else None

    def get_current_employment_status(self, instance) -> str | None:
        version = self._current_version(instance)
        return version.employment_status if version else None

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


class EmployeeSearchSummarySerializer(serializers.ModelSerializer):
    """Privacy-minimal identity projection for scoped employee pickers."""

    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ["id", "employee_number", "display_name"]

    def get_display_name(self, instance) -> str:
        preferred = instance.preferred_name or instance.first_name
        return f"{preferred} {instance.last_name}".strip()


class OrgChartNodeSerializer(serializers.ModelSerializer):
    """Compact current-position projection for the reporting topology.

    It deliberately omits contact, demographic, employment-status and other
    employee-detail fields. Row scope is applied to EmployeeVersion before
    this serializer runs, so a manager receives only their visible subtree.
    """

    employee_id = serializers.IntegerField(read_only=True)
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    display_name = serializers.SerializerMethodField()
    department = serializers.IntegerField(source="department_id", read_only=True)
    manager_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = EmployeeVersion
        fields = ["employee_id", "employee_number", "display_name", "job_title", "department", "manager_id"]
        read_only_fields = fields

    def get_display_name(self, instance) -> str:
        employee = instance.employee
        return f"{employee.preferred_name or employee.first_name} {employee.last_name}".strip()


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

    employee_name = serializers.SerializerMethodField()
    proposed_by_name = serializers.SerializerMethodField()
    confirmed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EmploymentChange
        fields = [
            "id", "employee", "employee_name", "change_type", "state", "effective_date", "reason",
            "proposed_by", "proposed_by_name", "proposed_at", "confirmed_by", "confirmed_by_name", "confirmed_at", "executed_at",
            "cancelled_by", "cancelled_at", "cancellation_reason",
            "lifts_suspension", "resulting_event",
        ]
        read_only_fields = [
            "state", "proposed_by", "proposed_at", "confirmed_by", "confirmed_at", "executed_at",
            "cancelled_by", "cancelled_at", "cancellation_reason",
            "lifts_suspension", "resulting_event",
        ]

    @staticmethod
    def _employee_name(employee) -> str | None:
        if employee is None:
            return None
        return f"{employee.preferred_name or employee.first_name} {employee.last_name}".strip()

    def get_employee_name(self, obj) -> str:
        return self._employee_name(obj.employee) or ""

    def get_proposed_by_name(self, obj) -> str | None:
        return self._employee_name(obj.proposed_by)

    def get_confirmed_by_name(self, obj) -> str | None:
        return self._employee_name(obj.confirmed_by)


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
