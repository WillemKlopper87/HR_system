from __future__ import annotations

from django.db import models

from core_hr.base import TimestampedModel

from .tiers import FieldTier


class Role(TimestampedModel):
    class RowScope(models.TextChoices):
        ALL = "all", "All records"
        OWN_TEAM = "own_team", "Own team (reporting line)"
        SELF = "self", "Self only"

    name = models.SlugField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    row_scope = models.CharField(max_length=20, choices=RowScope.choices)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.display_name


class RoleFieldTierGrant(TimestampedModel):
    """P/I/S/R read + write grants for a role (Data-Dictionary.md
    role.field_tiers). Grants are per-tier, not a single access
    threshold — a role can hold write access to Sensitive fields while
    having no access at all to Restricted ones (see RBAC-Roles.md)."""

    role = models.ForeignKey(Role, related_name="tier_grants", on_delete=models.CASCADE)
    tier = models.CharField(max_length=1, choices=FieldTier.choices)
    can_read = models.BooleanField(default=False)
    can_write = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["role", "tier"], name="one_grant_per_role_tier")
        ]
        ordering = ["role", "tier"]

    def __str__(self):
        return f"{self.role.name}/{self.tier}: read={self.can_read} write={self.can_write}"


class RoleAssignment(TimestampedModel):
    employee = models.ForeignKey(
        "core_hr.Employee", related_name="role_assignments", on_delete=models.CASCADE
    )
    role = models.ForeignKey(Role, related_name="assignments", on_delete=models.PROTECT)
    granted_by = models.ForeignKey(
        "core_hr.Employee",
        null=True,
        blank=True,
        related_name="granted_role_assignments",
        on_delete=models.SET_NULL,
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "role"],
                condition=models.Q(revoked_at__isnull=True),
                name="one_active_assignment_per_employee_role",
            )
        ]
        ordering = ["employee", "role"]

    def __str__(self):
        status = "active" if self.revoked_at is None else "revoked"
        return f"{self.employee.employee_number}: {self.role.name} ({status})"


class AuditLogEntry(models.Model):
    """Append-only. Every S/R-tier field read or write, and every access
    denial, produces one of these — the Sprint 2 acceptance criteria.
    Immutable at the ORM layer here; the production deployment additionally
    grants the app's DB role INSERT-only on this table (Architecture-Design.md §7)."""

    class Action(models.TextChoices):
        READ_SENSITIVE = "read_sensitive", "Read sensitive/restricted field(s)"
        ACCESS_DENIED = "access_denied", "Access denied"
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"
        EXPORT = "export", "Export"
        LOGIN = "login", "Login"
        PERMISSION_CHANGE = "permission_change", "Permission change"

    actor = models.ForeignKey(
        "core_hr.Employee",
        null=True,
        blank=True,
        related_name="audit_log_entries",
        on_delete=models.SET_NULL,
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    entity_type = models.CharField(max_length=200)
    entity_id = models.CharField(max_length=64, blank=True)
    field_tier = models.CharField(max_length=1, choices=FieldTier.choices)
    fields_touched = models.TextField(blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["actor", "timestamp"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        who = self.actor.employee_number if self.actor_id else "system"
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} {who} {self.action} {self.entity_type}#{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("AuditLogEntry records are append-only and cannot be modified")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("AuditLogEntry records are append-only and cannot be deleted")


class ConsentRecord(models.Model):
    """POPIA consent tracking for demographic self-ID and assessments
    (Data-Dictionary.md consent_record; gap C1). Withdrawal never deletes
    the record — it sets withdrawn_at, preserving the audit trail."""

    class Purpose(models.TextChoices):
        DEMOGRAPHIC_SELF_ID = "demographic_self_id", "Demographic self-identification"
        ASSESSMENT = "assessment", "Psychometric assessment"
        OTHER = "other", "Other"

    class LawfulBasis(models.TextChoices):
        CONSENT = "consent", "Consent"
        LEGAL_OBLIGATION_EEA = "legal_obligation_eea", "Legal obligation (Employment Equity Act)"

    employee = models.ForeignKey(
        "core_hr.Employee", related_name="consent_records", on_delete=models.CASCADE
    )
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    lawful_basis = models.CharField(max_length=30, choices=LawfulBasis.choices)
    granted_at = models.DateTimeField()
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    text_version = models.CharField(max_length=50)

    class Meta:
        ordering = ["-granted_at"]

    def __str__(self):
        status = "active" if self.withdrawn_at is None else "withdrawn"
        return f"{self.employee.employee_number}: {self.get_purpose_display()} ({status})"


class RetentionRule(TimestampedModel):
    """Per-entity retention metadata (Data-Dictionary.md retention_rule).
    Scheduled execution (a Celery job that anonymises/deletes per this
    table) is a follow-up build — out of Sprint 2's stated tasks."""

    class Action(models.TextChoices):
        ANONYMISE = "anonymise", "Anonymise"
        DELETE = "delete", "Delete"
        RETAIN = "retain", "Retain indefinitely"

    entity_type = models.CharField(max_length=200, unique=True)
    period_months = models.PositiveIntegerField()
    action = models.CharField(max_length=20, choices=Action.choices)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["entity_type"]

    def __str__(self):
        return f"{self.entity_type}: {self.get_action_display()} after {self.period_months}mo"
