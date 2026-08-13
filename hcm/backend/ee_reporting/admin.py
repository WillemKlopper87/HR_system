from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import EEPlan, EEQuestionnaire, EEReport, EmployerConfig, RemunerationRecord


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
