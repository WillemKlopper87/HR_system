from __future__ import annotations

from rbac_audit.drf import TieredModelSerializer, get_request_employee
from rbac_audit.permissions import has_row_access
from rest_framework import serializers

from .models import Feedback, Goal, Review, ReviewCycle


class ReviewCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewCycle
        fields = [
            "id", "name", "cycle_type", "status", "start_date", "end_date",
            "launched_at", "closed_at", "created_by",
        ]
        read_only_fields = ["status", "launched_at", "closed_at", "created_by"]


class GoalSerializer(TieredModelSerializer):
    """Goal is Internal-tier (Data-Dictionary.md), which every row-scope-
    qualifying role (employee/line_manager/hr_admin) reads generically —
    unlike Review/Feedback, there's no line_manager-blocking conflict here,
    so this can safely use the standard row-scoped tiered serializer."""

    class Meta:
        model = Goal
        fields = ["id", "employee", "manager", "title", "description", "target_date", "status", "created_by"]
        read_only_fields = ["created_by"]

    def validate(self, attrs):
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        target = attrs.get("employee") or getattr(self.instance, "employee", None)
        if target is not None and not has_row_access(requester, target):
            raise serializers.ValidationError("You don't have access to set goals for this employee.")
        return attrs


class ReviewSerializer(serializers.ModelSerializer):
    """Plain ModelSerializer, not TieredModelSerializer — see models.py's
    Review docstring for why. Object-level row-scope (RowScopePermission)
    is the access gate; write access to the self-/manager-review sections
    is further restricted to the specific reviewee/reviewer in validate()."""

    completion_status = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id", "review_cycle", "employee", "employee_name", "manager",
            "self_rating", "self_comments", "self_submitted_at",
            "manager_rating", "manager_comments", "manager_submitted_at",
            "completion_status",
        ]
        read_only_fields = ["review_cycle", "employee", "manager", "self_submitted_at", "manager_submitted_at"]

    def get_completion_status(self, obj) -> str:
        return obj.completion_status

    def get_employee_name(self, obj) -> str:
        employee = obj.employee
        return f"{employee.preferred_name or employee.first_name} {employee.last_name}".strip()

    def validate(self, attrs):
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        requester_id = requester.id if requester is not None else None
        instance = self.instance

        if {"self_rating", "self_comments"} & attrs.keys():
            if instance is None or instance.employee_id != requester_id:
                raise serializers.ValidationError("Only the reviewee can complete the self-review section.")
        if {"manager_rating", "manager_comments"} & attrs.keys():
            if instance is None or instance.manager_id != requester_id:
                raise serializers.ValidationError("Only the assigned manager can complete the manager-review section.")
        return attrs


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ["id", "employee", "author", "feedback_type", "text", "created_at"]
        read_only_fields = ["author", "feedback_type", "created_at"]
