from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from establishment.models import Position
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import CriticalPost, SuccessionCandidate

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Finance", code="FIN")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class SuccessionApiTestCase(TestCase):
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

        self.hr_admin = _hire("HR1", "succ_hradmin", "hr_admin")
        self.comp_manager = _hire("CM1", "succ_compmanager", "comp_manager")
        self.accounting_officer = _hire("AO1", "succ_accountingofficer", "accounting_officer")
        self.recruiter = _hire("REC1", "succ_recruiter", "recruiter")
        self.auditor = _hire("AUD1", "succ_auditor", "auditor")
        self.line_manager = _hire("LM1", "succ_manager", "line_manager")
        self.employee = _hire("EMP1", "succ_employee", "employee")

        self.approved_position = Position.objects.create(
            post_number="P-00001", title="Head of Finance", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        self.draft_position = Position.objects.create(
            post_number="P-00002", title="New Post", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )


class CriticalPostApiTests(SuccessionApiTestCase):
    def test_hr_admin_can_flag_an_approved_position(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/critical-posts/", {"position": self.approved_position.id, "reason": "Sole SME."}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["flagged_by"], self.hr_admin.id)

    def test_flagging_a_draft_position_is_rejected(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/critical-posts/", {"position": self.draft_position.id, "reason": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_line_manager_cannot_flag(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.post(
            "/api/v1/critical-posts/", {"position": self.approved_position.id, "reason": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_read_roles_can_list(self):
        CriticalPost.objects.create(position=self.approved_position, reason="x")
        for actor in (self.hr_admin, self.comp_manager, self.accounting_officer, self.auditor, self.recruiter):
            self.client.force_authenticate(user=actor.user)
            response = self.client.get("/api/v1/critical-posts/")
            self.assertEqual(response.status_code, 200, f"{actor.employee_number} should read")

    def test_line_manager_and_base_employee_cannot_list(self):
        CriticalPost.objects.create(position=self.approved_position, reason="x")
        for actor in (self.line_manager, self.employee):
            self.client.force_authenticate(user=actor.user)
            response = self.client.get("/api/v1/critical-posts/")
            self.assertEqual(response.status_code, 403, f"{actor.employee_number} should not read")

    def test_comp_manager_cannot_write(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/critical-posts/", {"position": self.approved_position.id, "reason": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 403)


class SuccessionCandidateApiTests(SuccessionApiTestCase):
    def setUp(self):
        super().setUp()
        self.critical_post = CriticalPost.objects.create(position=self.approved_position, reason="x")
        self.successor = Employee.objects.hire(
            employee_number="SUC1", first_name="Successor", last_name="Case", date_of_birth=date(1992, 1, 1),
            work_email="successor@example.com", hire_date=date(2022, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def _nominate(self, employee, readiness="ready_now"):
        self.client.force_authenticate(user=self.hr_admin.user)
        return self.client.post(
            "/api/v1/succession-candidates/",
            {"critical_post": self.critical_post.id, "employee": employee.id, "readiness": readiness},
            format="json",
        )

    def test_hr_admin_can_nominate(self):
        response = self._nominate(self.successor)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["nominated_by"], self.hr_admin.id)
        self.assertEqual(response.data["employee_name"], "SUC1 — Successor Case")

    def test_cannot_nominate_the_current_occupant(self):
        version = self.successor.current_version
        version.position = self.approved_position
        version.save(update_fields=["position"])
        response = self._nominate(self.successor)
        self.assertEqual(response.status_code, 400)

    def test_cannot_nominate_against_an_inactive_critical_post(self):
        self.critical_post.active = False
        self.critical_post.save(update_fields=["active"])
        response = self._nominate(self.successor)
        self.assertEqual(response.status_code, 400)

    def test_duplicate_active_nomination_rejected(self):
        first = self._nominate(self.successor)
        self.assertEqual(first.status_code, 201)
        second = self._nominate(self.successor, readiness="development_needed")
        self.assertEqual(second.status_code, 400)

    def test_withdraw_then_renominate_succeeds(self):
        first = self._nominate(self.successor)
        candidate_id = first.data["id"]
        self.client.force_authenticate(user=self.hr_admin.user)
        patch_response = self.client.patch(
            f"/api/v1/succession-candidates/{candidate_id}/", {"active": False}, format="json"
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.data)
        second = self._nominate(self.successor, readiness="ready_1_2_years")
        self.assertEqual(second.status_code, 201, second.data)

    def test_auditor_can_read_but_not_write(self):
        self._nominate(self.successor)
        self.client.force_authenticate(user=self.auditor.user)
        list_response = self.client.get("/api/v1/succession-candidates/")
        self.assertEqual(list_response.status_code, 200)
        write_response = self.client.post(
            "/api/v1/succession-candidates/",
            {"critical_post": self.critical_post.id, "employee": self.successor.id, "readiness": "ready_now"},
            format="json",
        )
        self.assertEqual(write_response.status_code, 403)

    def test_line_manager_cannot_read_even_their_own_report(self):
        self._nominate(self.successor)
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get("/api/v1/succession-candidates/")
        self.assertEqual(response.status_code, 403)

    def test_the_nominated_employees_own_login_cannot_read_it(self):
        self._nominate(self.successor)
        successor_user = User.objects.create_user(username="succ_successor", password="x")
        self.successor.user = successor_user
        self.successor.save(update_fields=["user"])
        RoleAssignment.objects.create(employee=self.successor, role=Role.objects.get(name="employee"))
        self.client.force_authenticate(user=successor_user)
        response = self.client.get("/api/v1/succession-candidates/")
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_cannot_see_their_own_row_even_though_they_hold_the_role(self):
        """spec §2.6/§5.2: no self-scope carve-out anywhere, including for
        hr_admin acting on their own login."""
        response = self._nominate(self.hr_admin)
        self.assertEqual(response.status_code, 201, response.data)
        candidate_id = response.data["id"]

        self.client.force_authenticate(user=self.hr_admin.user)
        list_response = self.client.get("/api/v1/succession-candidates/")
        ids = {row["id"] for row in list_response.data["results"]}
        self.assertNotIn(candidate_id, ids)

        retrieve_response = self.client.get(f"/api/v1/succession-candidates/{candidate_id}/")
        self.assertEqual(retrieve_response.status_code, 404)

    def test_candidate_card_surfaces_skills_and_performance_context(self):
        response = self._nominate(self.successor)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("skill_names", response.data)
        self.assertIn("latest_performance", response.data)
        self.assertEqual(response.data["skill_names"], [])
        self.assertIsNone(response.data["latest_performance"])
