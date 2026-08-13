from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import AssessmentAssignment, AssessmentResult, ProviderConfig


class AssessmentResultInline(admin.StackedInline):
    model = AssessmentResult
    extra = 0
    can_delete = False


@admin.register(AssessmentAssignment)
class AssessmentAssignmentAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "assessment_type", "provider_key", "status", "assigned_by", "completed_at")
    list_filter = ("assessment_type", "status", "provider_key")
    inlines = [AssessmentResultInline]


@admin.register(ProviderConfig)
class ProviderConfigAdmin(admin.ModelAdmin):
    list_display = ("provider_key", "display_name", "active")
    list_filter = ("active",)
