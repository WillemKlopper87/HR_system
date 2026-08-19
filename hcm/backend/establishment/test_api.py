# hcm/backend/establishment/test_api.py
from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Position

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class EstablishmentApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        def _hire(number, username, role_name):
            emp = Employee.objects.hire(
                employee_number=number, first_name=username.title(), last_name="Test", date_of_birth=date(1985, 1, 1),
                work_email=f"{username}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
                occupational_level=self.level, job_grade=self.grade, location=self.location,
                user=User.objects.create_user(username=username, password="x"),
            )
            RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name=role_name))
            return emp

        self.hr_admin = _hire("HR1", "est_hradmin", "hr_admin")
        self.comp_manager = _hire("CM1", "est_compmanager", "comp_manager")
        self.accounting_officer = _hire("AO1", "est_accountingofficer", "accounting_officer")
        self.recruiter = _hire("REC1", "est_recruiter", "recruiter")
        self.auditor = _hire("AUD1", "est_auditor", "auditor")
        self.line_manager = _hire("LM1", "est_manager", "line_manager")


@override_settings(POSITION_APPROVAL_CHAIN=["comp_manager", "accounting_officer"])
class PositionCreateAndChainApiTests(EstablishmentApiTestCase):
    def _propose(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post("/api/v1/positions/", {
            "title": "Software Engineer", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def test_recruiter_cannot_propose(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/positions/", {
            "title": "X", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id,
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_full_chain_via_api(self):
        position_id = self._propose()

        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/positions/{position_id}/submit/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "in_review")

        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(f"/api/v1/positions/{position_id}/decide/", {"decision": "approved"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "in_review")

        self.client.force_authenticate(user=self.accounting_officer.user)
        response = self.client.post(f"/api/v1/positions/{position_id}/decide/", {"decision": "approved"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "approved")

    def test_wrong_role_at_a_step_is_403_not_400(self):
        position_id = self._propose()
        self.client.force_authenticate(user=self.hr_admin.user)
        self.client.post(f"/api/v1/positions/{position_id}/submit/")

        self.client.force_authenticate(user=self.accounting_officer.user)  # step 0 needs comp_manager
        response = self.client.post(f"/api/v1/positions/{position_id}/decide/", {"decision": "approved"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_rejection_then_revise_via_api(self):
        position_id = self._propose()
        self.client.force_authenticate(user=self.hr_admin.user)
        self.client.post(f"/api/v1/positions/{position_id}/submit/")

        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            f"/api/v1/positions/{position_id}/decide/", {"decision": "rejected", "comment": "wrong grade"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "rejected")

        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/positions/{position_id}/revise/", {"title": "Senior Software Engineer"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["title"], "Senior Software Engineer")


class PositionReadAccessApiTests(EstablishmentApiTestCase):
    def setUp(self):
        super().setUp()
        self.approved = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        self.draft = Position.objects.create(
            post_number="P-00002", title="B", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )

    def test_hr_admin_sees_every_status(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/positions/")
        ids = {p["id"] for p in response.data["results"]}
        self.assertEqual(ids, {self.approved.id, self.draft.id})

    def test_recruiter_only_sees_approved(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get("/api/v1/positions/")
        ids = {p["id"] for p in response.data["results"]}
        self.assertEqual(ids, {self.approved.id})

    def test_line_manager_cannot_read(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get("/api/v1/positions/")
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_read(self):
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get("/api/v1/positions/")
        self.assertEqual(response.status_code, 200)
