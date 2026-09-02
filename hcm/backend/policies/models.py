from __future__ import annotations

from core_hr.base import TimestampedModel
from core_hr.models import Employee
from django.db import models
from simple_history.models import HistoricalRecords


class Policy(TimestampedModel):
    """An HR policy document — versioned the same way ee_reporting.EEReport
    is: `code` is the stable identity shared across every version of "the
    same" policy (e.g. every revision of the Leave Policy), `version` is a
    server-computed sequence within that code, and publishing a new
    version auto-archives whichever version was PUBLISHED before it
    (services.py::publish_policy). Never edited in place once published —
    a correction is a new draft version, not a silent rewrite, so an
    acknowledgment always points at an exact, immutable version."""

    class Category(models.TextChoices):
        CODE_OF_CONDUCT = "code_of_conduct", "Code of Conduct"
        LEAVE = "leave", "Leave Policy"
        IT_ACCEPTABLE_USE = "it_acceptable_use", "IT Acceptable Use"
        ANTI_HARASSMENT = "anti_harassment", "Anti-Harassment & Anti-Discrimination"
        HEALTH_SAFETY = "health_safety", "Health & Safety"
        REMOTE_WORK = "remote_work", "Remote Work"
        POPIA_PRIVACY = "popia_privacy", "POPIA / Data Privacy"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    code = models.SlugField(max_length=80)
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    body = models.TextField(blank=True)
    # The original uploaded document (PDF/DOCX/TXT), kept as the
    # authoritative source alongside the extracted `body` text — HR (and,
    # eventually, an audit) should be able to download exactly what was
    # published, not just its extracted-text rendering. Optional: `body`
    # can also be typed directly with no file at all.
    source_file = models.FileField(upload_to="policy_documents/%Y/%m/", null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    effective_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="policies_created"
    )
    published_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="policies_published"
    )
    published_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="unique_policy_code_version"),
        ]

    def __str__(self):
        return f"{self.title} v{self.version} ({self.get_status_display()})"


class PolicyAcknowledgment(TimestampedModel):
    """A personal attestation ("I have read and understood this policy")
    against one exact Policy version — always self-recorded, even for
    hr_admin, unlike e.g. compensation.BenefitsElection where HR
    legitimately records something on an employee's behalf. See
    policies/views.py::PolicyAcknowledgmentViewSet."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="policy_acknowledgments")
    policy = models.ForeignKey(Policy, on_delete=models.PROTECT, related_name="acknowledgments")
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-acknowledged_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "policy"], name="one_acknowledgment_per_employee_per_policy_version"
            )
        ]

    def __str__(self):
        return f"{self.employee.employee_number} acknowledged {self.policy.title} v{self.policy.version}"


class PolicyApproval(TimestampedModel):
    """One committee member's sign-off on a specific draft (services.py::
    publish_policy requires every CURRENT holder of the
    policy_committee_member role to have one of these before that draft
    can publish -- a live role check, not a roster snapshot, so someone
    added to or removed from the committee mid-review changes what
    publish requires next). Scoped to the exact Policy row (a specific
    version), matching PolicyAcknowledgment's own "points at an exact,
    immutable version" reasoning -- a new draft version needs fresh
    approvals, it does not inherit the previous version's."""

    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="approvals")
    approved_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="+")
    comment = models.TextField(blank=True)
    approved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-approved_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["policy", "approved_by"], name="one_approval_per_committee_member_per_policy"
            )
        ]

    def __str__(self):
        return f"{self.approved_by.employee_number} approved {self.policy.title} v{self.policy.version}"


class PolicyChunk(TimestampedModel):
    """A retrievable passage of one Policy version's body — the concrete
    data plumbing a future RAG/chatbot phase would embed and search over
    (see policies/chunking.py for the splitting strategy and
    Architecture-Design.md's Policy Q&A design note for the phased plan
    this is the first piece of: extraction -> chunking [here] ->
    embedding + retrieval -> chatbot). No embeddings or vector search
    exist yet — this table only stores the plain-text passages themselves,
    server-recomputed whenever a draft's body changes
    (services.py::_regenerate_chunks), never client-writable."""

    policy = models.ForeignKey(Policy, on_delete=models.CASCADE, related_name="chunks")
    sequence = models.PositiveIntegerField()
    text = models.TextField()

    class Meta:
        ordering = ["policy", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["policy", "sequence"], name="unique_policy_chunk_sequence"),
        ]

    def __str__(self):
        return f"{self.policy.title} v{self.policy.version} — chunk {self.sequence}"
