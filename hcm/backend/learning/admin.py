from django.contrib import admin

from .models import Certification, Course, CourseRequirement, EmployeeSkill, Skill, TrainingRecord


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "active")
    list_filter = ("category", "active")
    search_fields = ("name",)


@admin.register(EmployeeSkill)
class EmployeeSkillAdmin(admin.ModelAdmin):
    list_display = ("employee", "skill", "proficiency", "acquired_date")
    list_filter = ("proficiency", "skill")
    search_fields = ("employee__employee_number",)


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    list_display = ("employee", "name", "issuing_body", "issue_date", "expiry_date")
    search_fields = ("employee__employee_number", "name")


@admin.register(TrainingRecord)
class TrainingRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "title", "course", "status", "hours", "cost")
    list_filter = ("status",)
    search_fields = ("employee__employee_number", "title")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "provider", "mandatory", "validity_days", "active")
    list_filter = ("mandatory", "active")
    search_fields = ("name",)


@admin.register(CourseRequirement)
class CourseRequirementAdmin(admin.ModelAdmin):
    list_display = ("course", "department", "occupational_level", "effective_from", "due_within_days", "active")
    list_filter = ("active", "department", "occupational_level")
    search_fields = ("course__name",)
