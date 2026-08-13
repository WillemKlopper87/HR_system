from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import BiometricEnrollment, LivenessCheck


@admin.register(BiometricEnrollment)
class BiometricEnrollmentAdmin(SimpleHistoryAdmin):
    list_display = ("employee", "enrolled_by", "created_at")
    search_fields = ("employee__employee_number",)
    exclude = ("descriptor",)


@admin.register(LivenessCheck)
class LivenessCheckAdmin(admin.ModelAdmin):
    list_display = ("employee", "outcome", "at_office", "review_status", "created_at")
    list_filter = ("outcome", "review_status", "at_office", "trigger")
    search_fields = ("employee__employee_number",)
