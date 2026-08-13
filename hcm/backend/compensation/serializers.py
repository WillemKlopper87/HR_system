from __future__ import annotations

from rest_framework import serializers

from .models import Benefit, BenefitsElection, CompProposal, PayBand


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


class CompProposalSerializer(serializers.ModelSerializer):
    """employee/proposed_annual_salary/justification/effective_date are
    the only client-writable fields on create — current_job_grade,
    status, and requires_override are computed server-side by
    compensation/services.py::propose_compensation_change, not trusted
    from client input."""

    class Meta:
        model = CompProposal
        fields = [
            "id", "employee", "current_job_grade", "proposed_annual_salary", "justification",
            "status", "requires_override", "override_reason", "effective_date",
            "proposed_by", "approved_by", "approved_at",
        ]
        read_only_fields = [
            "current_job_grade", "status", "requires_override", "override_reason",
            "proposed_by", "approved_by", "approved_at",
        ]


class BenefitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Benefit
        fields = ["id", "name", "category", "description", "active"]


class BenefitsElectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BenefitsElection
        fields = ["id", "employee", "benefit", "status", "effective_date", "notes"]
