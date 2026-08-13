from __future__ import annotations

import json
from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rbac_audit.consent import record_consent
from rbac_audit.models import ConsentRecord, Role, RoleAssignment
from recruitment.models import Applicant, Requisition
from rest_framework.test import APIClient

from . import webhooks
from .models import AssessmentAssignment, ProviderConfig

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class AssessmentsApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        ProviderConfig.objects.create(provider_key="sandbox", display_name="Sandbox", active=True)

        def _hire(number, role_name, username):
            emp = Employee.objects.hire(
                employee_number=number, first_name=username.title(), last_name="Test", date_of_birth=date(1985, 1, 1),
                work_email=f"{username}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
                occupational_level=self.level, job_grade=self.grade, location=self.location,
                user=User.objects.create_user(username=username, password="x"),
            )
            RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name=role_name))
            return emp

        self.hr_admin = _hire("HR1", "hr_admin", "hradmin")
        self.ee_manager = _hire("EE1", "ee_manager", "eemanager")
        self.recruiter = _hire("REC1", "recruiter", "recruiter")
        self.line_manager = _hire("MGR1", "line_manager", "manager")
        self.auditor = _hire("AUD1", "auditor", "auditor")
        self.plain_employee = Employee.objects.hire(
            employee_number="E100", first_name="Plain", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="plain@example.com", hire_date=date(2021, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="plain", password="x"),
        )

        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN, opened_at=date(2026, 7, 1),
        )
        self.applicant = Applicant.objects.create(
            requisition=self.requisition, first_name="Cand", last_name="Idate",
            email="cand.idate@applicant-demo.example", date_of_birth=date(1995, 3, 3),
        )

    def _grant_employee_consent(self, employee):
        record_consent(
            employee=employee, purpose=ConsentRecord.Purpose.ASSESSMENT,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )

    def _grant_applicant_consent(self):
        record_consent(
            applicant=self.applicant, purpose=ConsentRecord.Purpose.ASSESSMENT,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )


class ModuleWidePermissionTests(AssessmentsApiTestCase):
    def setUp(self):
        super().setUp()
        self._grant_employee_consent(self.plain_employee)
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/", {"employee": self.plain_employee.id, "assessment_type": "cognitive"},
            format="json",
        )
        assert response.status_code == 201, response.data
        self.assignment_id = response.data["id"]

    def test_line_manager_gets_empty_list(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get("/api/v1/assessment-assignments/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_line_manager_gets_404_on_direct_id(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get(f"/api/v1/assessment-assignments/{self.assignment_id}/")
        self.assertEqual(response.status_code, 404)

    def test_subject_employee_sees_their_own_row(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/assessment-assignments/{self.assignment_id}/")
        self.assertEqual(response.status_code, 200)

    def test_ee_manager_sees_it(self):
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.get(f"/api/v1/assessment-assignments/{self.assignment_id}/")
        self.assertEqual(response.status_code, 200)

    def test_hr_admin_sees_it(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/assessment-assignments/{self.assignment_id}/")
        self.assertEqual(response.status_code, 200)

    def test_auditor_sees_it_read_only(self):
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get(f"/api/v1/assessment-assignments/{self.assignment_id}/")
        self.assertEqual(response.status_code, 200)

    def test_recruiter_does_not_see_employee_subject_row(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get(f"/api/v1/assessment-assignments/{self.assignment_id}/")
        self.assertEqual(response.status_code, 404)


class CreateAssignmentApiTests(AssessmentsApiTestCase):
    def test_create_without_consent_is_rejected(self):
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/", {"employee": self.plain_employee.id, "assessment_type": "cognitive"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_recruiter_cannot_create_employee_subject_assignment(self):
        self._grant_employee_consent(self.plain_employee)
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/", {"employee": self.plain_employee.id, "assessment_type": "cognitive"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_ee_manager_cannot_create_applicant_subject_assignment(self):
        self._grant_applicant_consent()
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/", {"applicant_id": self.applicant.id, "assessment_type": "technical"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_recruiter_can_create_applicant_subject_assignment_with_consent(self):
        self._grant_applicant_consent()
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/", {"applicant_id": self.applicant.id, "assessment_type": "technical"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["provider_key"], "sandbox")
        self.assertTrue(response.data["access_url"])

    def test_client_supplied_status_and_provider_fields_are_ignored(self):
        self._grant_employee_consent(self.plain_employee)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/",
            {
                "employee": self.plain_employee.id, "assessment_type": "cognitive",
                "status": "completed", "provider_key": "forged", "provider_reference": "forged-ref",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "assigned")
        self.assertEqual(response.data["provider_key"], "sandbox")
        self.assertNotEqual(response.data["provider_reference"], "forged-ref")


class ConsentActionApiTests(AssessmentsApiTestCase):
    def test_line_manager_cannot_capture_employee_consent(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/consent/", {"employee": self.plain_employee.id}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_ee_manager_can_capture_employee_consent(self):
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/consent/", {"employee": self.plain_employee.id}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            ConsentRecord.objects.filter(employee=self.plain_employee, purpose=ConsentRecord.Purpose.ASSESSMENT).exists()
        )

    def test_applicant_assessment_consent_via_recruitment_endpoint(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post(
            f"/api/v1/applicants/{self.applicant.id}/consent/", {"purpose": "assessment"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            ConsentRecord.objects.filter(applicant=self.applicant, purpose=ConsentRecord.Purpose.ASSESSMENT).exists()
        )


class SimulateCompletionApiTests(AssessmentsApiTestCase):
    def setUp(self):
        super().setUp()
        self._grant_employee_consent(self.plain_employee)
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/", {"employee": self.plain_employee.id, "assessment_type": "cognitive"},
            format="json",
        )
        self.assignment_id = response.data["id"]

    def test_simulate_completion_returns_a_result(self):
        response = self.client.post(f"/api/v1/assessment-assignments/{self.assignment_id}/simulate_completion/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "completed")
        self.assertTrue(response.data["result"]["summary"])

    def test_cannot_simulate_completion_twice(self):
        self.client.post(f"/api/v1/assessment-assignments/{self.assignment_id}/simulate_completion/")
        response = self.client.post(f"/api/v1/assessment-assignments/{self.assignment_id}/simulate_completion/")
        self.assertEqual(response.status_code, 400)

    def test_line_manager_cannot_simulate_completion(self):
        # 403, not 404: line_manager holds none of hr_admin/ee_manager/
        # recruiter, so CanAccessAssessmentAssignment.has_permission blocks
        # every write action outright, before any per-object lookup —
        # revealing nothing about whether this specific id exists.
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.post(f"/api/v1/assessment-assignments/{self.assignment_id}/simulate_completion/")
        self.assertEqual(response.status_code, 403)


class WebhookApiTests(AssessmentsApiTestCase):
    def setUp(self):
        super().setUp()
        self._grant_employee_consent(self.plain_employee)
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(
            "/api/v1/assessment-assignments/", {"employee": self.plain_employee.id, "assessment_type": "cognitive"},
            format="json",
        )
        self.provider_reference = response.data["provider_reference"]
        self.client.force_authenticate(user=None)

    def _post_webhook(self, payload, *, signature=None, timestamp=None):
        raw_body = json.dumps(payload).encode()
        ts = timestamp if timestamp is not None else int(timezone.now().timestamp())
        sig = signature if signature is not None else webhooks.sign_payload(raw_body, timestamp=ts)
        return self.client.post(
            "/webhooks/v1/assessments/", data=raw_body, content_type="application/json",
            HTTP_X_ASSESSMENT_SIGNATURE=sig, HTTP_X_ASSESSMENT_TIMESTAMP=str(ts),
        )

    def test_unsigned_request_is_rejected(self):
        response = self.client.post(
            "/webhooks/v1/assessments/",
            data=json.dumps({"provider_reference": self.provider_reference, "status": "completed"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_bad_signature_is_rejected(self):
        response = self._post_webhook(
            {"provider_reference": self.provider_reference, "status": "completed"}, signature="0" * 64
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_signature_updates_the_assignment(self):
        response = self._post_webhook(
            {"provider_reference": self.provider_reference, "status": "completed", "raw_score": "70", "summary": "Solid"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        assignment = AssessmentAssignment.objects.get(provider_reference=self.provider_reference)
        self.assertEqual(assignment.status, "completed")
        self.assertEqual(assignment.result.raw_score, "70")

    def test_unknown_provider_reference_returns_400(self):
        response = self._post_webhook({"provider_reference": "no-such-ref", "status": "completed"})
        self.assertEqual(response.status_code, 400)

    def test_get_method_not_allowed(self):
        response = self.client.get("/webhooks/v1/assessments/")
        self.assertEqual(response.status_code, 405)
