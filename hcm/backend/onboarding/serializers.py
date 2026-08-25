from __future__ import annotations

from rest_framework import serializers

from .models import ChecklistInstance, ChecklistInstanceItem, ChecklistTemplate, ChecklistTemplateItem


class ChecklistTemplateItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistTemplateItem
        fields = ["id", "template", "label", "description", "owner_role", "order"]


class ChecklistTemplateSerializer(serializers.ModelSerializer):
    """version/status/published_at/created_by are all computed server-side
    by services.py -- create_template auto-assigns version (spec section
    4.1), publish_template/retire_template own the status transition. Only
    name/direction are client-writable on create, same shape as
    EmploymentChangeSerializer's read-only-trail pattern."""

    items = ChecklistTemplateItemSerializer(many=True, read_only=True)

    class Meta:
        model = ChecklistTemplate
        fields = [
            "id", "name", "direction", "version", "status", "created_by", "published_at",
            "created_at", "items",
        ]
        read_only_fields = ["version", "status", "created_by", "published_at"]


class ChecklistInstanceItemSerializer(serializers.ModelSerializer):
    is_complete = serializers.BooleanField(read_only=True)

    class Meta:
        model = ChecklistInstanceItem
        fields = [
            "id", "instance", "label", "description", "owner_role", "order",
            "completed_by", "completed_at", "notes", "is_complete",
        ]
        read_only_fields = ["label", "description", "owner_role", "order", "completed_by", "completed_at", "notes"]


class ChecklistInstanceSerializer(serializers.ModelSerializer):
    """employee/direction (and optionally template, to pick a specific
    version) are the only client-writable fields on create ('manually
    create' -- see ChecklistInstanceViewSet.perform_create); everything
    else -- template_version, status, created_by, completed_at -- is
    computed server-side by services.create_checklist_instance, never
    trusted from client input (same shape as
    core_hr.EmploymentChangeSerializer)."""

    items = ChecklistInstanceItemSerializer(many=True, read_only=True)

    class Meta:
        model = ChecklistInstance
        fields = [
            "id", "employee", "template", "template_version", "direction", "status",
            "triggering_change", "created_by", "created_at", "completed_at", "items",
        ]
        read_only_fields = [
            "template_version", "status", "triggering_change", "created_by", "completed_at",
        ]
        extra_kwargs = {"template": {"required": False}}
