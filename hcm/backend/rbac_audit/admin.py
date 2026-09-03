from django.contrib import admin

from .models import (
    AuditLogEntry,
    ConsentRecord,
    RetentionRule,
    RetentionRuleRun,
    RetentionRun,
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


class RetentionRuleRunInline(admin.TabularInline):
    model = RetentionRuleRun
    extra = 0
    readonly_fields = ("entity_type", "action", "period_months", "cutoff", "status", "affected", "detail")
    can_delete = False


@admin.register(RetentionRun)
class RetentionRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "completed_at", "dry_run")
    list_filter = ("dry_run",)
    inlines = [RetentionRuleRunInline]


@admin.register(RetentionRuleRun)
class RetentionRuleRunAdmin(admin.ModelAdmin):
    """M-2's work-item surface: the ERROR/NO_HANDLER filter is where an
    operator finds every rule that didn't run cleanly, across every run,
    without having to open each RetentionRun individually."""

    list_display = ("run", "entity_type", "status", "affected", "action")
    list_filter = ("status", "entity_type")
    search_fields = ("entity_type",)
