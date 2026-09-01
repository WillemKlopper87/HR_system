from __future__ import annotations

from performance.queries import latest_final_score
from rest_framework import serializers

from .models import Benefit, BenefitsElection, CompCycle, CompProposal, PayBand
from .services import cycle_utilization


class PayBandSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayBand
        fields = [
            "id", "job_grade", "min_salary", "mid_salary", "max_salary", "valid_from", "valid_to", "created_by",
        ]
        read_only_fields = ["created_by"]

    def validate(self, attrs):
        get = lambda name: attrs.get(name, getattr(self.instance, name, None))  # noqa: E731
        min_salary, mid_salary, max_salary = get("min_salary"), get("mid_salary"), get("max_salary")
        if None not in (min_salary, mid_salary, max_salary) and not (min_salary <= mid_salary <= max_salary):
            raise serializers.ValidationError("Pay band must satisfy min ≤ mid ≤ max.")
        return attrs


class CompCycleSerializer(serializers.ModelSerializer):
    """`utilization` is a live, computed rollup (compensation/services.py::
    cycle_utilization) — never a stored field, so it can't drift out of
    sync with the proposals it summarizes (design spec §2.5)."""

    utilization = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    proposal_count = serializers.SerializerMethodField()

    class Meta:
        model = CompCycle
        fields = [
            "id", "name", "period_start", "period_end", "budget_amount", "department", "status",
            "status_display", "created_by", "closed_by", "closed_at", "utilization", "proposal_count",
        ]
        read_only_fields = ["status", "created_by", "closed_by", "closed_at"]

    def get_utilization(self, obj) -> dict:
        return cycle_utilization(obj)

    def get_proposal_count(self, obj) -> int:
        return obj.proposals.count()

    def validate(self, attrs):
        get = lambda name: attrs.get(name, getattr(self.instance, name, None))  # noqa: E731
        start, end = get("period_start"), get("period_end")
        if start is not None and end is not None and end <= start:
            raise serializers.ValidationError("period_end must be after period_start.")
        return attrs


class CompProposalSerializer(serializers.ModelSerializer):
    """employee/proposal_type/proposed_annual_salary/bonus_amount/cycle/
    justification/effective_date are the client-writable fields on
    create — current_job_grade, status, requires_override,
    exceeds_cycle_budget, baseline_salary_at_proposal are computed
    server-side by compensation/services.py::propose_compensation_change,
    not trusted from client input. `performance_context` is read-only
    informational context (design spec §2.8) from the pre-existing
    performance/queries.py seam — never an input to any calculation
    here."""

    performance_context = serializers.SerializerMethodField()
    employee_display = serializers.SerializerMethodField()
    # A plain DecimalField (not ReadOnlyField) so it string-coerces the
    # same way every other money field on this serializer already does
    # (proposed_annual_salary, bonus_amount, baseline_salary_at_proposal
    # are all model DecimalFields) -- DRF handles the property returning
    # None itself, never calling to_representation(None).
    budget_impact = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CompProposal
        fields = [
            "id", "employee", "employee_display", "current_job_grade", "proposal_type", "proposed_annual_salary", "bonus_amount",
            "baseline_salary_at_proposal", "budget_impact", "justification", "status", "requires_override",
            "exceeds_cycle_budget", "override_reason", "effective_date", "cycle",
            "proposed_by", "approved_by", "approved_at", "performance_context",
        ]
        read_only_fields = [
            "current_job_grade", "status", "requires_override", "exceeds_cycle_budget",
            "baseline_salary_at_proposal", "override_reason", "proposed_by", "approved_by", "approved_at",
        ]

    def get_performance_context(self, obj) -> dict | None:
        return latest_final_score(obj.employee_id)

    def get_employee_display(self, obj) -> str:
        return f"{obj.employee.employee_number} — {obj.employee.first_name} {obj.employee.last_name}"


class BenefitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Benefit
        fields = ["id", "name", "category", "description", "active"]


class BenefitsElectionSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = BenefitsElection
        fields = ["id", "employee", "employee_name", "benefit", "status", "effective_date", "notes"]

    def get_employee_name(self, obj) -> str:
        employee = obj.employee
        return f"{employee.preferred_name or employee.first_name} {employee.last_name}".strip()
