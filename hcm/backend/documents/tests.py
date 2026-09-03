from __future__ import annotations

from datetime import date

from core_hr.models import Department, Dependant, Employee, EmergencyContact, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rbac_audit.consent import record_consent
from rbac_audit.models import AuditLogEntry, ConsentRecord
from rbac_audit.tiers import FieldTier

from .models import DataSubjectRequest, EmployeeDocument
from .services import (
    DocumentError,
    complete_erasure_request,
    complete_export_request,
    decline_data_subject_request,
    delete_employee_document,
    submit_data_subject_request,
    upload_employee_document,
)

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class DocumentsServiceTestCase(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin-doc@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )
        self.employee = Employee.objects.hire(
            employee_number="E100", first_name="Staff", last_name="Member", date_of_birth=date(1992, 1, 1),
            work_email="staff-doc@example.com", personal_email="staff-personal@example.com", phone="0821111111",
            preferred_name="Staffy", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )

    def _pdf(self, name="doc.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.7\ncontent", content_type="application/pdf")


class UploadEmployeeDocumentTests(DocumentsServiceTestCase):
    def test_qualification_upload_succeeds_without_consent(self):
        document = upload_employee_document(
            self.employee, document_type=EmployeeDocument.DocumentType.QUALIFICATION,
            title="BCom Certificate", file=self._pdf(), actor=self.employee,
        )
        self.assertEqual(document.tier, FieldTier.INTERNAL)
        self.assertEqual(document.content_type, "application/pdf")

    def test_id_copy_upload_requires_consent(self):
        with self.assertRaises(DocumentError):
            upload_employee_document(
                self.employee, document_type=EmployeeDocument.DocumentType.ID_COPY,
                title="ID copy", file=self._pdf(), actor=self.employee,
            )

    def test_id_copy_upload_succeeds_once_consent_recorded(self):
        record_consent(
            employee=self.employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )
        document = upload_employee_document(
            self.employee, document_type=EmployeeDocument.DocumentType.ID_COPY,
            title="ID copy", file=self._pdf(), actor=self.employee,
        )
        self.assertEqual(document.tier, FieldTier.RESTRICTED)

    def test_disability_verification_requires_consent(self):
        with self.assertRaises(DocumentError):
            upload_employee_document(
                self.employee, document_type=EmployeeDocument.DocumentType.DISABILITY_VERIFICATION,
                title="Medical certificate", file=self._pdf(), actor=self.employee,
            )

    def test_employment_contract_requires_no_consent(self):
        document = upload_employee_document(
            self.employee, document_type=EmployeeDocument.DocumentType.EMPLOYMENT_CONTRACT,
            title="Signed contract", file=self._pdf(), actor=self.hr_admin,
        )
        self.assertEqual(document.tier, FieldTier.RESTRICTED)

    def test_invalid_document_type_rejected(self):
        with self.assertRaises(DocumentError):
            upload_employee_document(
                self.employee, document_type="not_a_type", title="x", file=self._pdf(), actor=self.employee,
            )

    def test_content_sniffing_rejects_mislabelled_file(self):
        """documents/validation.py — content-sniffed, not filename-trusted
        (design spec: the equivalent fix to policies/extraction.py's own)."""
        fake_pdf = SimpleUploadedFile("doc.pdf", b"not actually a pdf", content_type="application/pdf")
        with self.assertRaises(DocumentError):
            upload_employee_document(
                self.employee, document_type=EmployeeDocument.DocumentType.QUALIFICATION,
                title="Fake", file=fake_pdf, actor=self.employee,
            )

    def test_oversized_file_rejected(self):
        from .validation import MAX_DOCUMENT_SIZE_BYTES

        oversized = SimpleUploadedFile(
            "big.pdf", b"%PDF-1.7\n" + b"0" * (MAX_DOCUMENT_SIZE_BYTES + 1), content_type="application/pdf"
        )
        with self.assertRaises(DocumentError):
            upload_employee_document(
                self.employee, document_type=EmployeeDocument.DocumentType.QUALIFICATION,
                title="Big", file=oversized, actor=self.employee,
            )

    def test_delete_removes_row_and_is_audit_logged(self):
        document = upload_employee_document(
            self.employee, document_type=EmployeeDocument.DocumentType.QUALIFICATION,
            title="Cert", file=self._pdf(), actor=self.employee,
        )
        before = AuditLogEntry.objects.count()
        delete_employee_document(document, actor=self.hr_admin)
        self.assertFalse(EmployeeDocument.objects.filter(pk=document.pk).exists())
        self.assertGreater(AuditLogEntry.objects.count(), before)


class DataSubjectRequestServiceTests(DocumentsServiceTestCase):
    def test_duplicate_open_request_of_same_type_rejected(self):
        submit_data_subject_request(self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee)
        with self.assertRaises(DocumentError):
            submit_data_subject_request(self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee)

    def test_a_second_open_request_of_a_different_type_is_allowed(self):
        submit_data_subject_request(self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee)
        # Should not raise.
        submit_data_subject_request(self.employee, request_type=DataSubjectRequest.RequestType.ERASURE, actor=self.employee)

    def test_decline_marks_request_declined_without_touching_data(self):
        request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.ERASURE, actor=self.employee
        )
        decline_data_subject_request(request, actor=self.hr_admin, notes="Not enough detail.")
        request.refresh_from_db()
        self.assertEqual(request.status, DataSubjectRequest.Status.DECLINED)

    def test_cannot_act_on_a_non_submitted_request_twice(self):
        request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.ERASURE, actor=self.employee
        )
        decline_data_subject_request(request, actor=self.hr_admin)
        with self.assertRaises(DocumentError):
            decline_data_subject_request(request, actor=self.hr_admin)

    def test_export_generates_downloadable_file(self):
        upload_employee_document(
            self.employee, document_type=EmployeeDocument.DocumentType.QUALIFICATION,
            title="Cert", file=self._pdf(), actor=self.employee,
        )
        request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee
        )
        complete_export_request(request, actor=self.hr_admin)
        request.refresh_from_db()
        self.assertEqual(request.status, DataSubjectRequest.Status.COMPLETED)
        self.assertTrue(request.export_file)
        content = request.export_file.read().decode()
        self.assertIn("E100", content)
        self.assertIn("Cert", content)

    def test_export_cannot_run_on_erasure_request(self):
        request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.ERASURE, actor=self.employee
        )
        with self.assertRaises(DocumentError):
            complete_export_request(request, actor=self.hr_admin)


class SubjectExportRegistryIntegrationTests(DocumentsServiceTestCase):
    """HCM remediation H-3: complete_export_request() now goes through
    rbac_audit.subject_export's domain registry rather than documents'
    own hardcoded field list being the entire export."""

    def test_export_includes_compensation_and_learning_domains(self):
        from compensation.models import PayBand
        from compensation.services import propose_compensation_change
        from learning.models import TrainingRecord

        PayBand.objects.create(
            job_grade=self.employee.current_version.job_grade, min_salary=100000, mid_salary=150000, max_salary=200000,
            valid_from=date(2020, 1, 1),
        )
        propose_compensation_change(employee=self.employee, proposed_annual_salary=180000, proposed_by=self.hr_admin)
        TrainingRecord.objects.create(
            employee=self.employee, title="First Aid", status=TrainingRecord.Status.COMPLETED,
        )

        request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee
        )
        complete_export_request(request, actor=self.hr_admin)
        request.refresh_from_db()

        self.assertEqual(request.status, DataSubjectRequest.Status.COMPLETED)
        self.assertEqual(request.export_manifest["compensation.CompProposal"]["status"], "included")
        self.assertEqual(request.export_manifest["learning.TrainingRecord"]["status"], "included")
        content = request.export_file.read().decode()
        self.assertIn("180000", content)
        self.assertIn("First Aid", content)

    def test_manifest_identifies_no_record_domains(self):
        request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee
        )
        complete_export_request(request, actor=self.hr_admin)
        request.refresh_from_db()

        self.assertEqual(request.export_manifest["compensation.CompProposal"]["status"], "no_records")
        self.assertEqual(request.export_manifest["learning.TrainingRecord"]["status"], "no_records")

    def test_export_cannot_be_marked_completed_when_a_required_domain_fails(self):
        from rbac_audit import subject_export

        def boom(employee):
            raise RuntimeError("simulated domain outage")

        request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee
        )
        with subject_export.temporary_handler("test.Flaky", boom):
            complete_export_request(request, actor=self.hr_admin)
        request.refresh_from_db()

        self.assertEqual(request.status, DataSubjectRequest.Status.PARTIALLY_COMPLETED)
        self.assertEqual(request.export_manifest["test.Flaky"]["status"], "failed")
        # documents' own domain still succeeded and is still in the file.
        self.assertEqual(request.export_manifest["documents.core_bundle"]["status"], "included")

    def test_a_non_required_domain_failing_does_not_block_completion(self):
        from rbac_audit import subject_export

        def boom(employee):
            raise RuntimeError("simulated non-critical outage")

        request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee
        )
        with subject_export.temporary_handler("test.OptionalFlaky", boom, required=False):
            complete_export_request(request, actor=self.hr_admin)
        request.refresh_from_db()

        self.assertEqual(request.status, DataSubjectRequest.Status.COMPLETED)
        self.assertEqual(request.export_manifest["test.OptionalFlaky"]["status"], "failed")


class ErasureAllowListTests(DocumentsServiceTestCase):
    """Design spec §6.1 — the heart of the POPIA design decision: erasure
    is a hardcoded allow-list, and everything outside it must survive
    completely untouched, no matter what."""

    def setUp(self):
        super().setUp()
        record_consent(
            employee=self.employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )
        self.document = upload_employee_document(
            self.employee, document_type=EmployeeDocument.DocumentType.ID_COPY,
            title="ID copy", file=self._pdf(), actor=self.employee,
        )
        self.dependant = Dependant.objects.create(
            employee=self.employee, first_name="Jane", last_name="Member", relationship=Dependant.Relationship.SPOUSE
        )
        self.contact = EmergencyContact.objects.create(employee=self.employee, name="Jane", phone="0821234567")
        self.request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.ERASURE, actor=self.employee
        )

    def test_erasure_deletes_documents_dependants_and_contacts(self):
        complete_erasure_request(self.request, actor=self.hr_admin)
        self.assertFalse(EmployeeDocument.objects.filter(pk=self.document.pk).exists())
        self.assertFalse(Dependant.objects.filter(pk=self.dependant.pk).exists())
        self.assertFalse(EmergencyContact.objects.filter(pk=self.contact.pk).exists())

    def test_erasure_clears_only_the_three_named_optional_fields(self):
        complete_erasure_request(self.request, actor=self.hr_admin)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.preferred_name, "")
        self.assertEqual(self.employee.personal_email, "")
        self.assertEqual(self.employee.phone, "")

    def test_erasure_never_touches_statutory_identity_fields(self):
        complete_erasure_request(self.request, actor=self.hr_admin)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.employee_number, "E100")
        self.assertEqual(self.employee.work_email, "staff-doc@example.com")
        self.assertEqual(self.employee.hire_date, date(2021, 1, 1))

    def test_erasure_never_touches_employment_history_or_audit_log(self):
        from core_hr.models import EmploymentEvent

        before_events = list(EmploymentEvent.objects.filter(employee=self.employee).values_list("id", flat=True))
        before_audit_count = AuditLogEntry.objects.count()
        complete_erasure_request(self.request, actor=self.hr_admin)
        after_events = list(EmploymentEvent.objects.filter(employee=self.employee).values_list("id", flat=True))
        self.assertEqual(before_events, after_events)
        # Erasure itself adds audit entries (it's logged like everything
        # else) — the assertion is that no *existing* entry was removed.
        self.assertGreaterEqual(AuditLogEntry.objects.count(), before_audit_count)
        self.assertEqual(AuditLogEntry.objects.filter(action=AuditLogEntry.Action.DELETE, entity_type__startswith="rbac_audit").count(), 0)

    def test_erasure_withdraws_but_does_not_delete_the_consent_record(self):
        complete_erasure_request(self.request, actor=self.hr_admin)
        consent = ConsentRecord.objects.get(employee=self.employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS)
        self.assertIsNotNone(consent.withdrawn_at)

    def test_erasure_marks_request_completed(self):
        complete_erasure_request(self.request, actor=self.hr_admin, notes="Actioned per POPIA request.")
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, DataSubjectRequest.Status.COMPLETED)
        self.assertEqual(self.request.resolution_notes, "Actioned per POPIA request.")

    def test_erasure_cannot_run_on_export_request(self):
        export_request = submit_data_subject_request(
            self.employee, request_type=DataSubjectRequest.RequestType.EXPORT, actor=self.employee
        )
        with self.assertRaises(DocumentError):
            complete_erasure_request(export_request, actor=self.hr_admin)
