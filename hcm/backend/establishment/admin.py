from django.contrib import admin

from .models import Position, PositionApprovalStep


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("post_number", "title", "department", "status", "current_step")
    list_filter = ("status", "department")
    search_fields = ("post_number", "title")


@admin.register(PositionApprovalStep)
class PositionApprovalStepAdmin(admin.ModelAdmin):
    list_display = ("position", "step_index", "role", "actor", "decision", "created_at")
    list_filter = ("decision", "role")
