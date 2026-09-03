"""Service layer for employee documents and the POPIA data-subject request
workflow. Design spec: docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md

No role/permission checks here — same 403-vs-400 split core_hr/exits.py's
module docstring argues for: wrong role is a view-layer 403
(documents/permissions.py, documents/views.py), wrong state/missing
consent is a DocumentError -> 400. Every state-changing function is atomic
and audit-logged via rbac_audit's log_access, matching exits.py's and
onboarding/services.py's own convention."""
from __future__ import annotations

import json

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from core_hr.models import Employee
from rbac_audit.audit import log_access
from rbac_audit.consent import has_active_consent, withdraw_consent
from rbac_audit.models import AuditLogEntry, ConsentRecord
from rbac_audit.subject_export import DomainExportResult, DomainStatus, run_subject_export
from rbac_audit.tiers import FieldTier

from .models import DataSubjectRequest, EmployeeDocument
from .validation import DocumentValidationError, validate_upload

# Spec §6.1: the ONLY optional Employee fields erasure may clear — exactly
# RBAC-Roles.md's own "ESS-editable fields (contact details...)" set
# (core_hr/serializers.py::ESS_EDITABLE_FIELDS). Deliberately hardcoded
# here rather than imported, so a future change to ESS_EDITABLE_FIELDS
# doesn't silently widen what erasure is allowed to touch.
ERASABLE_EMPLOYEE_FIELDS = ("preferred_name", "personal_email", "phone")


class DocumentError(ValueError):
    """Raised for state-machine violations: an invalid document_type,
    missing required consent, or acting on a DataSubjectRequest that isn't
    in the state the action expects."""


def _log(*, actor, entity_type, entity_id, tier, detail) -> None:
    log_access(
        actor=actor, action=AuditLogEntry.Action.UPDATE, entity_type=entity_type,
        entity_id=entity_id, field_tier=tier, fields_touched=detail,
    )


# --- EmployeeDocument -----------------------------------------------------

@transaction.atomic
def upload_employee_document(
    employee, *, document_type, title, file, description="", actor=None
) -> EmployeeDocument:
    if document_type not in EmployeeDocument.DocumentType.values:
        raise DocumentError(f"'{document_type}' is not a valid document type.")
    try:
        content_type = validate_upload(file)
    except DocumentValidationError as exc:
        raise DocumentError(str(exc)) from exc

    if document_type in EmployeeDocument.CONSENT_REQUIRED_TYPES and not has_active_consent(
        employee=employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS
    ):
        raise DocumentError(
            "Employee document consent has not been captured — "
            "POST /api/v1/employee-documents/consent/ first."
        )

    document = EmployeeDocument.objects.create(
        employee=employee, document_type=document_type, title=title, description=description,
        file=file, content_type=content_type, size_bytes=file.size, uploaded_by=actor,
    )
    _log(
        actor=actor, entity_type="documents.EmployeeDocument", entity_id=document.id, tier=document.tier,
        detail=f"uploaded {document_type} document {title!r} for {employee.employee_number}",
    )
    return document


@transaction.atomic
def delete_employee_document(document: EmployeeDocument, *, actor=None) -> None:
    entity_id = document.id
    employee_number = document.employee.employee_number
    document_type = document.document_type
    tier = document.tier
    document.file.delete(save=False)
    document.delete()
    _log(
        actor=actor, entity_type="documents.EmployeeDocument", entity_id=entity_id, tier=tier,
        detail=f"deleted {document_type} document for {employee_number}",
    )


# --- DataSubjectRequest ----------------------------------------------------

@transaction.atomic
def submit_data_subject_request(employee, *, request_type, notes="", actor=None) -> DataSubjectRequest:
    if request_type not in DataSubjectRequest.RequestType.values:
        raise DocumentError(f"'{request_type}' is not a valid request type.")
    if DataSubjectRequest.objects.filter(
        employee=employee, request_type=request_type, status=DataSubjectRequest.Status.SUBMITTED
    ).exists():
        raise DocumentError(
            f"{employee.employee_number} already has an open {request_type} request awaiting action."
        )
    request = DataSubjectRequest.objects.create(
        employee=employee, request_type=request_type, request_notes=notes, requested_by=actor,
    )
    _log(
        actor=actor, entity_type="documents.DataSubjectRequest", entity_id=request.id, tier=FieldTier.SENSITIVE,
        detail=f"submitted a {request_type} request for {employee.employee_number}",
    )
    return request


def _assert_submitted(request: DataSubjectRequest) -> None:
    if request.status != DataSubjectRequest.Status.SUBMITTED:
        raise DocumentError(f"Cannot act on a request in '{request.status}' state.")


@transaction.atomic
def decline_data_subject_request(request: DataSubjectRequest, *, actor, notes="") -> DataSubjectRequest:
    _assert_submitted(request)
    request.status = DataSubjectRequest.Status.DECLINED
    request.reviewed_by = actor
    request.reviewed_at = timezone.now()
    request.resolution_notes = notes
    request.save(update_fields=["status", "reviewed_by", "reviewed_at", "resolution_notes"])
    _log(
        actor=actor, entity_type="documents.DataSubjectRequest", entity_id=request.id, tier=FieldTier.SENSITIVE,
        detail=f"declined {request.request_type} request for {request.employee.employee_number}",
    )
    return request


def _serialise_for_export(employee: Employee) -> dict:
    """Spec §6.4: everything `documents` + the kernel (core_hr, rbac_audit)
    can assemble directly, without a new peer-app import. Registered as
    the "documents.core_bundle" domain in rbac_audit.subject_export's
    registry (HCM remediation H-3) rather than being the whole export by
    itself — learning/performance/compensation/etc. are separate domains
    registered from their own apps; this function's scope is unchanged."""
    version_history = [
        {
            "valid_from": v.valid_from.isoformat(),
            "valid_to": v.valid_to.isoformat() if v.valid_to else None,
            "department": v.department.name if v.department_id else None,
            "job_title": v.job_title,
            "employment_status": v.employment_status,
        }
        for v in employee.versions.order_by("valid_from")
    ]
    documents = [
        {
            "document_type": d.document_type,
            "title": d.title,
            "uploaded_at": d.created_at.isoformat(),
            "content_type": d.content_type,
        }
        for d in employee.documents.all()
    ]
    dependants = [
        {
            "first_name": d.first_name, "last_name": d.last_name,
            "relationship": d.relationship, "date_of_birth": d.date_of_birth.isoformat() if d.date_of_birth else None,
        }
        for d in employee.dependants.all()
    ]
    emergency_contacts = [
        {"name": c.name, "relationship": c.relationship, "phone": c.phone, "email": c.email, "is_primary": c.is_primary}
        for c in employee.emergency_contacts.all()
    ]
    consents = [
        {
            "purpose": c.purpose, "lawful_basis": c.lawful_basis,
            "granted_at": c.granted_at.isoformat(),
            "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None,
        }
        for c in employee.consent_records.all()
    ]
    requests = [
        {"request_type": r.request_type, "status": r.status, "requested_at": r.requested_at.isoformat()}
        for r in employee.data_subject_requests.all()
    ]
    return {
        "generated_at": timezone.now().isoformat(),
        "employee": {
            "employee_number": employee.employee_number,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "preferred_name": employee.preferred_name,
            "work_email": employee.work_email,
            "personal_email": employee.personal_email,
            "phone": employee.phone,
            "hire_date": employee.hire_date.isoformat(),
        },
        "employment_history": version_history,
        "documents": documents,
        "dependants": dependants,
        "emergency_contacts": emergency_contacts,
        "consent_records": consents,
        "data_subject_requests": requests,
    }


def _core_bundle_export_handler(employee: Employee) -> DomainExportResult:
    """rbac_audit.subject_export registry entry for "documents.core_bundle"
    (HCM remediation H-3) -- registered from DocumentsConfig.ready()."""
    payload = _serialise_for_export(employee)
    return DomainExportResult(status=DomainStatus.INCLUDED, record_count=1, payload=payload)


@transaction.atomic
def complete_export_request(request: DataSubjectRequest, *, actor, notes="") -> DataSubjectRequest:
    _assert_submitted(request)
    if request.request_type != DataSubjectRequest.RequestType.EXPORT:
        raise DocumentError("This is not an export request.")

    domain_payloads, manifest = run_subject_export(request.employee)
    export_document = {
        "generated_at": timezone.now().isoformat(),
        "manifest": manifest.as_dict(),
        "domains": domain_payloads,
    }
    filename = f"export-{request.employee.employee_number}-{timezone.now():%Y%m%d%H%M%S}.json"
    request.export_file.save(filename, ContentFile(json.dumps(export_document, indent=2)), save=False)
    request.export_manifest = manifest.as_dict()
    # HCM remediation H-3: COMPLETED now means every REQUIRED domain
    # actually succeeded, not merely that documents' own portion did --
    # PARTIALLY_COMPLETED still ships whatever domains DID succeed (an
    # incomplete export today beats blocking the subject's statutory
    # right entirely on one domain's transient failure) but says so, in a
    # status an operator can query and act on.
    request.status = (
        DataSubjectRequest.Status.COMPLETED if manifest.complete else DataSubjectRequest.Status.PARTIALLY_COMPLETED
    )
    request.reviewed_by = actor
    request.reviewed_at = timezone.now()
    request.resolution_notes = notes
    request.save(update_fields=[
        "export_file", "export_manifest", "status", "reviewed_by", "reviewed_at", "resolution_notes",
    ])
    log_access(
        actor=actor, action=AuditLogEntry.Action.EXPORT, entity_type="documents.DataSubjectRequest",
        entity_id=request.id, field_tier=FieldTier.RESTRICTED,
        fields_touched=f"personal data export ({request.status}) generated for {request.employee.employee_number}",
    )
    return request


@transaction.atomic
def complete_erasure_request(request: DataSubjectRequest, *, actor, notes="") -> DataSubjectRequest:
    """Spec §6.1 — the allow-list, and ONLY the allow-list. Never consults
    rbac_audit.RetentionRule: a generic "delete whatever isn't RETAIN-
    ruled" implementation would be one missing/misconfigured rule away
    from deleting EmploymentEvent/EmploymentChange/AuditLogEntry, exactly
    what the employment-exit-states spec's non-destructive philosophy
    exists to prevent. What this touches is hardcoded and closed."""
    _assert_submitted(request)
    if request.request_type != DataSubjectRequest.RequestType.ERASURE:
        raise DocumentError("This is not an erasure request.")
    employee = request.employee

    document_count = employee.documents.count()
    for document in list(employee.documents.all()):
        document.file.delete(save=False)
    employee.documents.all().delete()
    if document_count:
        _log(
            actor=actor, entity_type="documents.EmployeeDocument", entity_id=employee.id, tier=FieldTier.RESTRICTED,
            detail=f"erased {document_count} document(s) for {employee.employee_number} (request #{request.pk})",
        )

    dependant_count = employee.dependants.count()
    employee.dependants.all().delete()
    if dependant_count:
        _log(
            actor=actor, entity_type="core_hr.Dependant", entity_id=employee.id, tier=FieldTier.SENSITIVE,
            detail=f"erased {dependant_count} dependant(s) for {employee.employee_number} (request #{request.pk})",
        )

    contact_count = employee.emergency_contacts.count()
    employee.emergency_contacts.all().delete()
    if contact_count:
        _log(
            actor=actor, entity_type="core_hr.EmergencyContact", entity_id=employee.id, tier=FieldTier.SENSITIVE,
            detail=f"erased {contact_count} emergency contact(s) for {employee.employee_number} (request #{request.pk})",
        )

    cleared = [f for f in ERASABLE_EMPLOYEE_FIELDS if getattr(employee, f)]
    if cleared:
        for field in cleared:
            setattr(employee, field, "")
        employee.save(update_fields=list(cleared))
        _log(
            actor=actor, entity_type="core_hr.Employee", entity_id=employee.id, tier=FieldTier.INTERNAL,
            detail=f"cleared {', '.join(cleared)} for {employee.employee_number} (request #{request.pk})",
        )

    consent_qs = ConsentRecord.objects.filter(
        employee=employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS, withdrawn_at__isnull=True
    )
    for consent in consent_qs:
        withdraw_consent(consent, actor=actor)

    request.status = DataSubjectRequest.Status.COMPLETED
    request.reviewed_by = actor
    request.reviewed_at = timezone.now()
    request.resolution_notes = notes
    request.save(update_fields=["status", "reviewed_by", "reviewed_at", "resolution_notes"])
    return request
