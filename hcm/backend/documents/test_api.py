from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rbac_audit.models import ConsentRecord, Role, RoleAssignment
from rest_framework.test import APIClient

from .models import DataSubjectRequest, EmployeeDocument

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class DocumentsApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        def hire(number, username, **extra):
            return Employee.objects.hire(
                employee_number=number, first_name=username, last_name="Test", date_of_birth=date(1985, 1, 1),
                work_email=f"{username}@example.com", hire_date=date(2015, 1, 1), department=dept,
                occupational_level=level, job_grade=grade, location=location,
                user=User.objects.create_user(username=username, password="x"), **extra,
            )

        self.hr_admin = hire("HR1", "hradmin-doc-api")
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.employee = hire("E100", "staff-doc-api")
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="employee"))

        self.manager = hire("M100", "manager-doc-api")
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))
        version = self.employee.current_version
        version.manager = self.manager
        version.save(update_fields=["manager"])

        self.ee_manager = hire("EE1", "eemanager-doc-api")
        RoleAssignment.objects.create(employee=self.ee_manager, role=Role.objects.get(name="ee_manager"))

        self.comp_manager = hire("CM1", "compmanager-doc-api")
        RoleAssignment.objects.create(employee=self.comp_manager, role=Role.objects.get(name="comp_manager"))

        self.auditor = hire("AU1", "auditor-doc-api")
        RoleAssignment.objects.create(employee=self.auditor, role=Role.objects.get(name="auditor"))

        self.stranger = hire("S1", "stranger-doc-api")
        RoleAssignment.objects.create(employee=self.stranger, role=Role.objects.get(name="employee"))

    def _pdf(self, name="doc.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.7\ncontent", content_type="application/pdf")

    def _upload(self, employee, document_type, actor_user, title="A document"):
        self.client.force_authenticate(user=actor_user)
        return self.client.post(
            "/api/v1/employee-documents/",
            {"employee": employee.id, "document_type": document_type, "title": title, "file": self._pdf()},
            format="multipart",
        )


class EmployeeDocumentPermissionTests(DocumentsApiTestCase):
    def test_employee_can_upload_own_qualification(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.QUALIFICATION, self.employee.user)
        self.assertEqual(response.status_code, 201, response.data)

    def test_line_manager_cannot_upload_document_for_report(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.QUALIFICATION, self.manager.user)
        self.assertEqual(response.status_code, 400, response.data)

    def test_hr_admin_can_upload_id_copy_with_consent(self):
        ConsentRecord.objects.create(
            employee=self.employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, granted_at="2026-01-01T00:00:00Z", text_version="v1",
        )
        response = self._upload(self.employee, EmployeeDocument.DocumentType.ID_COPY, self.hr_admin.user)
        self.assertEqual(response.status_code, 201, response.data)

    def test_id_copy_upload_without_consent_is_rejected(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.ID_COPY, self.hr_admin.user)
        self.assertEqual(response.status_code, 400, response.data)

    def test_consent_action_records_consent_then_unblocks_upload(self):
        self.client.force_authenticate(user=self.employee.user)
        consent_response = self.client.post("/api/v1/employee-documents/consent/", {"employee": self.employee.id})
        self.assertEqual(consent_response.status_code, 201, consent_response.data)
        response = self._upload(self.employee, EmployeeDocument.DocumentType.ID_COPY, self.employee.user)
        self.assertEqual(response.status_code, 201, response.data)

    def test_stranger_cannot_read_others_qualification(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.QUALIFICATION, self.employee.user)
        document_id = response.data["id"]
        self.client.force_authenticate(user=self.stranger.user)
        response = self.client.get(f"/api/v1/employee-documents/{document_id}/")
        self.assertEqual(response.status_code, 403)

    def test_line_manager_reads_internal_tier_qualification_for_report(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.QUALIFICATION, self.employee.user)
        document_id = response.data["id"]
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get(f"/api/v1/employee-documents/{document_id}/")
        self.assertEqual(response.status_code, 200)

    def test_line_manager_cannot_read_restricted_tier_employment_contract(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.EMPLOYMENT_CONTRACT, self.hr_admin.user)
        document_id = response.data["id"]
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get(f"/api/v1/employee-documents/{document_id}/")
        self.assertEqual(response.status_code, 403)

    def test_comp_manager_reads_restricted_tier_employment_contract(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.EMPLOYMENT_CONTRACT, self.hr_admin.user)
        document_id = response.data["id"]
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.get(f"/api/v1/employee-documents/{document_id}/")
        self.assertEqual(response.status_code, 200)

    def test_ee_manager_reads_sensitive_tier_disability_verification(self):
        ConsentRecord.objects.create(
            employee=self.employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, granted_at="2026-01-01T00:00:00Z", text_version="v1",
        )
        response = self._upload(
            self.employee, EmployeeDocument.DocumentType.DISABILITY_VERIFICATION, self.hr_admin.user
        )
        document_id = response.data["id"]
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.get(f"/api/v1/employee-documents/{document_id}/")
        self.assertEqual(response.status_code, 200)

    def test_comp_manager_cannot_read_sensitive_tier_disability_verification(self):
        ConsentRecord.objects.create(
            employee=self.employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, granted_at="2026-01-01T00:00:00Z", text_version="v1",
        )
        response = self._upload(
            self.employee, EmployeeDocument.DocumentType.DISABILITY_VERIFICATION, self.hr_admin.user
        )
        document_id = response.data["id"]
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.get(f"/api/v1/employee-documents/{document_id}/")
        self.assertEqual(response.status_code, 403)

    def test_download_requires_same_permission_as_retrieve(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.QUALIFICATION, self.employee.user)
        document_id = response.data["id"]
        self.client.force_authenticate(user=self.stranger.user)
        response = self.client.get(f"/api/v1/employee-documents/{document_id}/download/")
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(user=self.employee.user)
        response = self.client.get(f"/api/v1/employee-documents/{document_id}/download/")
        self.assertEqual(response.status_code, 200)

    def test_list_excludes_tiers_the_requester_cannot_read(self):
        self._upload(self.employee, EmployeeDocument.DocumentType.QUALIFICATION, self.employee.user)
        ConsentRecord.objects.create(
            employee=self.employee, purpose=ConsentRecord.Purpose.EMPLOYEE_DOCUMENTS,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, granted_at="2026-01-01T00:00:00Z", text_version="v1",
        )
        self._upload(self.employee, EmployeeDocument.DocumentType.ID_COPY, self.hr_admin.user)

        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get(f"/api/v1/employee-documents/?employee={self.employee.id}")
        self.assertEqual(response.status_code, 200)
        types = {row["document_type"] for row in response.data["results"]}
        self.assertEqual(types, {"qualification"})

    def test_employee_can_delete_own_document(self):
        response = self._upload(self.employee, EmployeeDocument.DocumentType.QUALIFICATION, self.employee.user)
        document_id = response.data["id"]
        self.client.force_authenticate(user=self.employee.user)
        response = self.client.delete(f"/api/v1/employee-documents/{document_id}/")
        self.assertEqual(response.status_code, 204)


class DataSubjectRequestApiTests(DocumentsApiTestCase):
    def test_employee_can_submit_export_request(self):
        self.client.force_authenticate(user=self.employee.user)
        response = self.client.post(
            "/api/v1/data-subject-requests/", {"employee": self.employee.id, "request_type": "export"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_stranger_cannot_submit_request_for_another_employee(self):
        self.client.force_authenticate(user=self.stranger.user)
        response = self.client.post(
            "/api/v1/data-subject-requests/", {"employee": self.employee.id, "request_type": "export"}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_hr_admin_can_file_on_behalf_of_employee(self):
        """Design spec §6.3 — the ex-employee-can't-log-in-anymore case."""
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/data-subject-requests/",
            {"employee": self.employee.id, "request_type": "erasure", "request_notes": "Phoned in, no ESS access."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["requested_by_number"], "HR1")

    def test_non_hr_admin_cannot_complete_a_request(self):
        request = DataSubjectRequest.objects.create(employee=self.employee, request_type="export", requested_by=self.employee)
        self.client.force_authenticate(user=self.employee.user)
        response = self.client.post(f"/api/v1/data-subject-requests/{request.id}/complete/")
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_completes_export_request_and_can_download_it(self):
        request = DataSubjectRequest.objects.create(employee=self.employee, request_type="export", requested_by=self.employee)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/data-subject-requests/{request.id}/complete/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "completed")

        response = self.client.get(f"/api/v1/data-subject-requests/{request.id}/download/")
        self.assertEqual(response.status_code, 200)

    def test_hr_admin_can_decline_a_request(self):
        request = DataSubjectRequest.objects.create(employee=self.employee, request_type="erasure", requested_by=self.employee)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/data-subject-requests/{request.id}/decline/", {"resolution_notes": "Insufficient info."})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "declined")

    def test_auditor_can_list_all_requests_read_only(self):
        DataSubjectRequest.objects.create(employee=self.employee, request_type="export", requested_by=self.employee)
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get("/api/v1/data-subject-requests/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_stranger_only_sees_own_requests_in_list(self):
        DataSubjectRequest.objects.create(employee=self.employee, request_type="export", requested_by=self.employee)
        self.client.force_authenticate(user=self.stranger.user)
        response = self.client.get("/api/v1/data-subject-requests/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])
