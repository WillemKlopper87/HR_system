from __future__ import annotations

from rbac_audit.drf import TieredModelSerializer, get_request_employee
from rbac_audit.permissions import has_row_access
from rest_framework import serializers

from .models import Certification, Course, CourseRequirement, EmployeeSkill, Skill, TrainingRecord


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ["id", "name", "category", "description", "active"]


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "name", "provider", "description", "hours", "mandatory", "validity_days", "active"]


class CourseRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseRequirement
        fields = [
            "id", "course", "department", "occupational_level", "effective_from", "due_within_days", "active",
        ]

    def validate(self, attrs):
        course = attrs.get("course") or getattr(self.instance, "course", None)
        if course is not None and not course.mandatory:
            raise serializers.ValidationError(
                "Course must be marked mandatory in the catalogue before a requirement rule can target it."
            )

        department = attrs.get("department", getattr(self.instance, "department", None))
        occupational_level = attrs.get("occupational_level", getattr(self.instance, "occupational_level", None))
        active = attrs.get("active", getattr(self.instance, "active", True))
        if course is not None and active:
            duplicate = CourseRequirement.objects.filter(
                course=course, department=department, occupational_level=occupational_level, active=True,
            )
            if self.instance is not None:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError(
                    "An active requirement already exists for this course and this exact department/"
                    "occupational-level scope."
                )
        return attrs


class RowScopedLearningSerializer(TieredModelSerializer):
    """Shared validate() for EmployeeSkill/Certification/TrainingRecord:
    self, your manager (own_team), or hr_admin can create/edit an entry
    for a given employee — same row-scope check as performance.Goal
    (Sprint 6). Internal-tier fields have no line_manager-blocking
    conflict (unlike performance.Review's Sensitive-tier ones), so this
    safely uses the standard tiered path."""

    def validate(self, attrs):
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        target = attrs.get("employee") or getattr(self.instance, "employee", None)
        if target is not None and not has_row_access(requester, target):
            raise serializers.ValidationError("You don't have access to manage learning records for this employee.")
        return attrs


class EmployeeSkillSerializer(RowScopedLearningSerializer):
    class Meta:
        model = EmployeeSkill
        fields = ["id", "employee", "skill", "proficiency", "acquired_date", "notes"]


class CertificationSerializer(RowScopedLearningSerializer):
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Certification
        fields = ["id", "employee", "name", "issuing_body", "credential_id", "issue_date", "expiry_date", "is_expired"]


class TrainingRecordSerializer(RowScopedLearningSerializer):
    class Meta:
        model = TrainingRecord
        fields = [
            "id", "employee", "title", "provider", "course", "status", "start_date", "completion_date",
            "hours", "cost", "learning_programme_category", "learner_agreement_signed",
            "evidence_file", "evidence_content_type", "evidence_sha256",
        ]
        read_only_fields = ["evidence_content_type", "evidence_sha256"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        requester = get_request_employee(request) if request is not None else None
        target = attrs.get("employee") or getattr(self.instance, "employee", None)
        is_self_submission = requester is not None and target is not None and requester.id == target.id

        if is_self_submission:
            if self.instance is None:
                # A self-submitted enrollment is always a REQUEST — the
                # server decides the starting status, not the client, and
                # nothing beyond title/provider/start_date is trusted from
                # a self-submission (hours/cost/completion_date are what a
                # manager/hr_admin fills in once it's actually approved).
                attrs["status"] = TrainingRecord.Status.REQUESTED
                attrs.pop("hours", None)
                attrs.pop("cost", None)
                attrs.pop("completion_date", None)
            else:
                disallowed = {"status", "hours", "cost", "completion_date"} & attrs.keys()
                if disallowed:
                    raise serializers.ValidationError(
                        "Only your manager or hr_admin can update status/hours/cost/completion date."
                    )
        return attrs
