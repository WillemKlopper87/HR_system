from __future__ import annotations

import learning.queries as learning_queries
import performance.queries as performance_queries
from establishment.models import Position
from rest_framework import serializers

from .models import CriticalPost, SuccessionCandidate


class CriticalPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = CriticalPost
        fields = ["id", "position", "reason", "active", "flagged_by", "created_at", "updated_at"]
        read_only_fields = ["flagged_by"]

    def validate(self, attrs):
        position = attrs.get("position") or getattr(self.instance, "position", None)
        if position is not None and position.status != Position.Status.APPROVED:
            raise serializers.ValidationError(
                "Only an approved position can be flagged as succession-critical (spec §4.1)."
            )
        return attrs


class SuccessionCandidateSerializer(serializers.ModelSerializer):
    """`skill_names`/`latest_performance` are read-only cross-app context
    (spec §2.7) -- informational only, never an input to `readiness`, which
    is always the human judgement call HR records directly."""

    skill_names = serializers.SerializerMethodField()
    latest_performance = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = SuccessionCandidate
        fields = [
            "id", "critical_post", "employee", "employee_name", "readiness", "notes", "nominated_by", "active",
            "skill_names", "latest_performance", "created_at", "updated_at",
        ]
        read_only_fields = ["nominated_by"]

    def get_skill_names(self, obj) -> list[str]:
        return learning_queries.skill_names_for_employee(obj.employee_id)

    def get_latest_performance(self, obj) -> dict | None:
        return performance_queries.latest_final_score(obj.employee_id)

    def get_employee_name(self, obj) -> str:
        employee = obj.employee
        name = f"{employee.preferred_name or employee.first_name} {employee.last_name}".strip()
        return f"{employee.employee_number} — {name}"

    def validate(self, attrs):
        critical_post = attrs.get("critical_post") or getattr(self.instance, "critical_post", None)
        employee = attrs.get("employee") or getattr(self.instance, "employee", None)
        active = attrs.get("active", getattr(self.instance, "active", True))

        if critical_post is not None and not critical_post.active:
            raise serializers.ValidationError(
                "This post is not currently flagged succession-critical -- flag it first."
            )

        if critical_post is not None and employee is not None:
            occupant_version = critical_post.position.current_occupant
            if occupant_version is not None and occupant_version.employee_id == employee.id:
                raise serializers.ValidationError("An employee cannot be their own successor.")

        if critical_post is not None and employee is not None and active:
            duplicate = SuccessionCandidate.objects.filter(critical_post=critical_post, employee=employee, active=True)
            if self.instance is not None:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError(
                    "This employee already has an active nomination for this critical post."
                )
        return attrs
