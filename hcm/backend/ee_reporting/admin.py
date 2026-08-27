from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    EEForumMeeting,
    EEForumMember,
    EEPlan,
    EEPlanMeasure,
    EEPlanProgressSnapshot,
    EEQuestionnaire,
    EEReport,
    EESector,
    EmployerConfig,
    RemunerationRecord,
)


@admin.register(EESector)
class EESectorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "disability_target_pct")


@admin.register(EEForumMember)
class EEForumMemberAdmin(SimpleHistoryAdmin):
    list_display = ("employee", "representation", "role", "term_start", "term_end")


@admin.register(EEForumMeeting)
class EEForumMeetingAdmin(SimpleHistoryAdmin):
    list_display = ("meeting_date", "title", "report_year")


@admin.register(EEPlanMeasure)
class EEPlanMeasureAdmin(SimpleHistoryAdmin):
    list_display = ("plan", "category", "owner", "target_end", "status")
    list_filter = ("status", "category")


@admin.register(EEPlanProgressSnapshot)
class EEPlanProgressSnapshotAdmin(admin.ModelAdmin):
    list_display = ("plan", "as_of", "disability_pct", "taken_by")


@admin.register(EmployerConfig)
class EmployerConfigAdmin(SimpleHistoryAdmin):
    list_display = ("trade_name", "business_type", "employee_count_band")


@admin.register(EEPlan)
class EEPlanAdmin(SimpleHistoryAdmin):
    list_display = ("plan_period_start", "plan_period_end", "created_by")


@admin.register(EEQuestionnaire)
class EEQuestionnaireAdmin(SimpleHistoryAdmin):
    list_display = ("report_year", "achieved_all_targets", "achieved_annual_objectives")


@admin.register(RemunerationRecord)
class RemunerationRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "period_start", "period_end", "fixed_remuneration", "variable_remuneration")
    list_filter = ("period_start", "period_end")
    search_fields = ("employee__employee_number",)


@admin.register(EEReport)
class EEReportAdmin(admin.ModelAdmin):
    list_display = ("form_type", "report_year", "version", "status", "generated_at")
    list_filter = ("form_type", "status", "report_year")
