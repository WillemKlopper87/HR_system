"""Employee documents (tiered, consent-aware, authenticated download) and
the POPIA data-subject export/erasure request workflow. Design spec:
docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md"""
from __future__ import annotations

from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

from core_hr.base import TimestampedModel
from core_hr.models import Employee
from rbac_audit.tiers import FieldTier


class EmployeeDocument(TimestampedModel):
    """Spec §2.6: sensitivity varies BY ROW (an ID copy and a qualification
    certificate are not equally sensitive despite sharing this model and
    its `file` field), so unlike every other tiered model in this codebase
    `tier` is a computed property driven by `document_type`, not a
    rbac_audit.tiers.FIELD_TIERS entry — those map model.field -> tier for
    a fixed schema, which doesn't fit a per-row sensitivity. See
    documents/permissions.py for the read-side row-tier gate this implies."""

    class DocumentType(models.TextChoices):
        ID_COPY = "id_copy", "ID copy"
        QUALIFICATION = "qualification", "Qualification / certificate"
        EMPLOYMENT_CONTRACT = "employment_contract", "Employment contract"
        DISABILITY_VERIFICATION = "disability_verification", "Disability verification"
        OTHER = "other", "Other"

    # Spec §2.6 table.
    DOCUMENT_TYPE_TIERS = {
        DocumentType.ID_COPY: FieldTier.RESTRICTED,
        DocumentType.EMPLOYMENT_CONTRACT: FieldTier.RESTRICTED,
        DocumentType.DISABILITY_VERIFICATION: FieldTier.SENSITIVE,
        DocumentType.QUALIFICATION: FieldTier.INTERNAL,
        DocumentType.OTHER: FieldTier.SENSITIVE,
    }
    # Spec §2.7: consent (rbac_audit.ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS)
    # is required before upload for exactly these two types.
    CONSENT_REQUIRED_TYPES = {DocumentType.ID_COPY, DocumentType.DISABILITY_VERIFICATION}

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="employee_documents/%Y/%m/")
    # Server-sniffed (documents/validation.py) — never client-trusted, same
    # discipline policies/extraction.py established for policy uploads.
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="employee_documents_uploaded"
    )
    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.get_document_type_display()} — {self.title}"

    @property
    def tier(self) -> str:
        return self.DOCUMENT_TYPE_TIERS.get(self.document_type, FieldTier.SENSITIVE)


class DataSubjectRequest(TimestampedModel):
    """The POPIA workflow itself (spec §4.2, §6). Both request types are
    reviewed and actioned by hr_admin — never auto-executed — precisely
    because ERASURE's allow-list (documents/services.py::execute_erasure)
    has to hold the non-destructive philosophy from the employment-exit-
    states spec §6.3 (employment history, audit logs, anything under an
    existing RETAIN rule must never be touched) in tension with POPIA's
    erasure right (spec §6.1)."""

    class RequestType(models.TextChoices):
        EXPORT = "export", "Export my data"
        ERASURE = "erasure", "Erasure request"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        COMPLETED = "completed", "Completed"
        DECLINED = "declined", "Declined"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="data_subject_requests")
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    # Usually == employee (self-submitted); set to the filing hr_admin when
    # the subject can no longer log in themselves (spec §6.3 — the exit
    # cascade already disabled their login) or is otherwise reaching out
    # through an out-of-band channel.
    requested_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="data_subject_requests_filed"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    request_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="data_subject_requests_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    # Populated only when an EXPORT request completes (services.py::
    # generate_export) — never set for an ERASURE request.
    export_file = models.FileField(upload_to="data_subject_exports/%Y/%m/", null=True, blank=True)

    class Meta:
        ordering = ["-requested_at"]
        constraints = [
            # Mirrors onboarding.ChecklistInstance's "one active checklist
            # per employee per direction" shape — don't let a second
            # identical request pile up while the first is unactioned.
            models.UniqueConstraint(
                fields=["employee", "request_type"],
                condition=Q(status="submitted"),
                name="one_open_data_subject_request_per_employee_per_type",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_number}: {self.get_request_type_display()} ({self.status})"
