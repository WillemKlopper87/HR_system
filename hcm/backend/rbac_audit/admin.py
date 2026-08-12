from django.contrib import admin

from .models import (
    AuditLogEntry,
    ConsentRecord,
    RetentionRule,
    Role,
    RoleAssignment,
    RoleFieldTierGrant,
)


class RoleFieldTierGrantInline(admin.TabularInline):
    model = RoleFieldTierGrant
    extra = 0


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "display_name", "row_scope", "active")
    search_fields = ("name", "display_name")
    inlines = [RoleFieldTierGrantInline]


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("employee", "role", "granted_at", "revoked_at")
    list_filter = ("role",)
    search_fields = ("employee__employee_number", "employee__first_name", "employee__last_name")


@admin.register(AuditLogEntry)
class AuditLogEntryAdmin(admin.ModelAdmin):
    """Read-only in admin — entries are append-only (see model)."""

    list_display = ("timestamp", "actor", "action", "entity_type", "entity_id", "field_tier")
    list_filter = ("action", "field_tier")
    search_fields = ("entity_type", "entity_id", "actor__employee_number")
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "purpose", "lawful_basis", "granted_at", "withdrawn_at")
    list_filter = ("purpose", "lawful_basis")
    search_fields = ("employee__employee_number",)


@admin.register(RetentionRule)
class RetentionRuleAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "period_months", "action", "active")
