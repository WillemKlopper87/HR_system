from __future__ import annotations

from django.db import models

from core_hr.base import TimestampedModel

from .fields import EncryptedCharField
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
        STEP_UP_GRANTED = "step_up_granted", "Step-up authentication granted"

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
        # `-id` is a tiebreaker: `timestamp` (auto_now_add) doesn't have
        # enough resolution to guarantee uniqueness between entries created
        # in quick succession (e.g. in tests, or two log_access() calls in
        # the same request) — without it, "-timestamp" alone lets rows that
        # share a timestamp come back in either order non-deterministically.
        ordering = ["-timestamp", "-id"]
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
    (Data-Dictionary.md consent_record: "employee or applicant (FK, one
    of)"; gap C1). Withdrawal never deletes the record — it sets
    withdrawn_at, preserving the audit trail. One shared table for both
    pre-hire (recruitment's applicant demographic capture, Sprint 4) and
    post-hire (ESS self-ID, Sprint 15) consent, per the Data Dictionary,
    rather than two divergent tables."""

    class Purpose(models.TextChoices):
        DEMOGRAPHIC_SELF_ID = "demographic_self_id", "Demographic self-identification"
        ASSESSMENT = "assessment", "Psychometric assessment"
        BIOMETRIC = "biometric", "Biometric identity + attendance-location verification"
        # C2 (docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md
        # §2.7) — gates uploading an id_copy/disability_verification
        # documents.EmployeeDocument, kept distinct from DEMOGRAPHIC_SELF_ID
        # so a POPIA erasure request can withdraw exactly this consent
        # without touching the separate self-ID answer on EmployeeVersion.
        EMPLOYEE_DOCUMENTS = "employee_documents", "Employee document storage (ID copy, disability verification)"
        OTHER = "other", "Other"

    class LawfulBasis(models.TextChoices):
        CONSENT = "consent", "Consent"
        LEGAL_OBLIGATION_EEA = "legal_obligation_eea", "Legal obligation (Employment Equity Act)"

    employee = models.ForeignKey(
        "core_hr.Employee", null=True, blank=True, related_name="consent_records", on_delete=models.CASCADE
    )
    applicant = models.ForeignKey(
        "recruitment.Applicant", null=True, blank=True, related_name="consent_records", on_delete=models.CASCADE
    )
    purpose = models.CharField(max_length=30, choices=Purpose.choices)
    lawful_basis = models.CharField(max_length=30, choices=LawfulBasis.choices)
    granted_at = models.DateTimeField()
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    text_version = models.CharField(max_length=50)

    class Meta:
        ordering = ["-granted_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(employee__isnull=False, applicant__isnull=True)
                    | models.Q(employee__isnull=True, applicant__isnull=False)
                ),
                name="consentrecord_exactly_one_subject",
            )
        ]

    def __str__(self):
        subject = self.employee.employee_number if self.employee_id else f"applicant#{self.applicant_id}"
        status = "active" if self.withdrawn_at is None else "withdrawn"
        return f"{subject}: {self.get_purpose_display()} ({status})"


class TOTPDevice(TimestampedModel):
    """One authenticator-app device per employee (RFC 6238 TOTP), used for
    step-up authentication before viewing Restricted-tier payroll data
    (Data-Dictionary.md: compensation.pay_band/comp_proposal and
    ee_reporting.remuneration_record are all "R") — ordinary session
    login is not sufficient for that data. Not the same thing as ADR-004's
    planned Entra ID SSO: that's how you get INTO the app; this is an
    extra, deliberate step for a narrow set of Restricted-tier endpoints
    once you're already in, mirroring how re-entering a reason for a
    disruptive action (e.g. a server shutdown) is a distinct UX moment
    from the login that got you shell access in the first place."""

    employee = models.OneToOneField(
        "core_hr.Employee", related_name="totp_device", on_delete=models.CASCADE
    )
    # Base32 (pyotp.random_base32()) — not itself a password, but treated
    # as sensitive: a leaked secret lets someone generate valid codes
    # without the physical device. HCM remediation H-4: encrypted at rest
    # via rbac_audit.fields.EncryptedCharField (see core_hr.models.core.
    # Employee's national_id_number comment for the phase-2 cutover rationale).
    secret = EncryptedCharField(purpose="totp_seed", blank=True, default="")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        status = "confirmed" if self.confirmed_at else "pending confirmation"
        return f"{self.employee.employee_number} TOTP device ({status})"


class StepUpGrant(TimestampedModel):
    """A time-boxed unlock of one Restricted-tier scope, obtained by
    entering a valid TOTP code AND selecting a business-justification
    reason together — both required in the same request, not two
    separate steps a client could split and only do one of. Expires after
    STEPUP_GRANT_MINUTES (services.py) — a new grant (new code, new
    justification) is required after that, not a silent renewal, so a
    grant obtained for a specific stated reason can't quietly cover an
    entire day's unrelated browsing."""

    class Scope(models.TextChoices):
        PAYROLL_DATA = "payroll_data", "Payroll / compensation data"

    class Reason(models.TextChoices):
        PAYROLL_PROCESSING = "payroll_processing", "Payroll processing or audit"
        EMPLOYEE_QUERY = "employee_query", "Employee query or dispute resolution"
        COMPLIANCE_REPORTING = "compliance_reporting", "Compliance or regulatory reporting"
        SYSTEM_TROUBLESHOOTING = "system_troubleshooting", "System troubleshooting"
        OTHER = "other", "Other (specify)"

    employee = models.ForeignKey(
        "core_hr.Employee", related_name="step_up_grants", on_delete=models.CASCADE
    )
    scope = models.CharField(max_length=30, choices=Scope.choices)
    reason = models.CharField(max_length=30, choices=Reason.choices)
    reason_detail = models.TextField(blank=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-granted_at"]
        indexes = [models.Index(fields=["employee", "scope", "expires_at"])]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.scope} until {self.expires_at:%Y-%m-%d %H:%M}"


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


class RetentionRun(TimestampedModel):
    """HCM remediation M-2: one row per retention.run_retention() call.
    Before this model, a run's outcome existed only as retention.py's
    in-memory `RetentionRunResult` list (returned to the caller and
    discarded) and log lines -- an `error` or `no_handler` rule was
    invisible to anyone not tailing logs at the moment it happened. This
    and RetentionRuleRun below give the same run a durable, queryable
    record, without changing run_retention()'s existing return contract
    (still the same in-memory list; every existing caller is unaffected)."""

    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    dry_run = models.BooleanField(default=False)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"retention run {self.started_at.isoformat()}{' (dry run)' if self.dry_run else ''}"


class RetentionRuleRun(TimestampedModel):
    """One rule's outcome within a RetentionRun -- mirrors
    retention.RetentionRunResult's fields, persisted."""

    class RunStatus(models.TextChoices):
        OK = "ok", "OK"
        SKIPPED = "skipped", "Skipped"
        NO_HANDLER = "no_handler", "No handler registered"
        ERROR = "error", "Error"

    run = models.ForeignKey(RetentionRun, related_name="rule_runs", on_delete=models.CASCADE)
    entity_type = models.CharField(max_length=200)
    action = models.CharField(max_length=20)
    period_months = models.PositiveIntegerField()
    cutoff = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=RunStatus.choices)
    affected = models.PositiveIntegerField(default=0)
    detail = models.TextField(blank=True)

    class Meta:
        ordering = ["entity_type"]

    def __str__(self):
        return f"{self.run_id}: {self.entity_type} ({self.status})"
