from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Policy, PolicyAcknowledgment


@admin.register(Policy)
class PolicyAdmin(SimpleHistoryAdmin):
    list_display = ("title", "code", "version", "status", "category", "published_at")
    list_filter = ("status", "category")
    search_fields = ("title", "code")


@admin.register(PolicyAcknowledgment)
class PolicyAcknowledgmentAdmin(admin.ModelAdmin):
    list_display = ("employee", "policy", "acknowledged_at")
    search_fields = ("employee__employee_number", "policy__title")
