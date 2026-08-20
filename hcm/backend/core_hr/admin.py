from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    ContractRenewalDecision,
    DataQualityException,
    Department,
    Employee,
    EmployeeVersion,
    EmploymentEvent,
    JobGrade,
    Location,
    OccupationalLevel,
)


class EmployeeVersionInline(admin.TabularInline):
    model = EmployeeVersion
    fk_name = "employee"
    extra = 0
    fields = (
        "valid_from", "valid_to", "department", "occupational_level", "job_grade",
        "manager", "employment_status", "location", "contract_end_date",
    )
    show_change_link = True
    can_delete = False


@admin.register(Employee)
class EmployeeAdmin(SimpleHistoryAdmin):
    list_display = ("employee_number", "first_name", "last_name", "work_email", "hire_date")
    search_fields = ("employee_number", "first_name", "last_name", "work_email")
    inlines = [EmployeeVersionInline]


@admin.register(EmployeeVersion)
class EmployeeVersionAdmin(SimpleHistoryAdmin):
    list_display = ("employee", "valid_from", "valid_to", "department", "occupational_level", "employment_status")
    list_filter = ("department", "occupational_level", "employment_status")
    search_fields = ("employee__employee_number", "employee__first_name", "employee__last_name")


@admin.register(EmploymentEvent)
class EmploymentEventAdmin(SimpleHistoryAdmin):
    list_display = ("employee", "event_type", "effective_date", "termination_reason")
    list_filter = ("event_type",)
    search_fields = ("employee__employee_number",)


@admin.register(Department)
class DepartmentAdmin(SimpleHistoryAdmin):
    list_display = ("code", "name", "parent", "active")
    search_fields = ("code", "name")


@admin.register(OccupationalLevel)
class OccupationalLevelAdmin(SimpleHistoryAdmin):
    list_display = ("code", "name", "order", "active")
    ordering = ("order",)


@admin.register(JobGrade)
class JobGradeAdmin(SimpleHistoryAdmin):
    list_display = ("code", "name", "occupational_level", "active")
    search_fields = ("code", "name")


@admin.register(Location)
class LocationAdmin(SimpleHistoryAdmin):
    list_display = ("code", "name", "province", "active")
    search_fields = ("code", "name")


@admin.register(ContractRenewalDecision)
class ContractRenewalDecisionAdmin(SimpleHistoryAdmin):
    list_display = ("employee_version", "status", "recommended_action", "decided_action")
    list_filter = ("status",)
    search_fields = ("employee_version__employee__employee_number",)


@admin.register(DataQualityException)
class DataQualityExceptionAdmin(admin.ModelAdmin):
    list_display = ("employee", "exception_type", "detected_at", "resolved_at")
    list_filter = ("exception_type",)
    search_fields = ("employee__employee_number",)
