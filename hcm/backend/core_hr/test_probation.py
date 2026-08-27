from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.models import AuditLogEntry, Role, RoleAssignment
from rest_framework.test import APIClient

from .models import ProbationPeriod, ProbationReview

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class ProbationApiTestCase(TestCase):
    # Code on integrating EE into HR practice, probation section:
    # documented reviews signed by the employee, completion rates by
    # designated group, exit interviews for non-confirmations --
    # deliberately split out of the fixed-term contract-tracking slice
    # since probation applies to permanent hires too.

    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR9", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin9@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin9", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.manager = Employee.objects.hire(
            employee_number="MGR9", first_name="Line", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="manager9@example.com", hire_date=date(2018, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="manager9", password="x"),
        )
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))

        self.report = Employee.objects.hire(
            employee_number="E900", first_name="New", last_name="Hire", date_of_birth=date(1995, 1, 1),
            work_email="newhire9@example.com", hire_date=date(2026, 6, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location, manager=self.manager,
            employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
            user=User.objects.create_user(username="newhire9", password="x"),
        )
        RoleAssignment.objects.create(employee=self.report, role=Role.objects.get(name="employee"))

        self.outsider = Employee.objects.hire(
            employee_number="OUT9", first_name="Out", last_name="Sider", date_of_birth=date(1990, 1, 1),
            work_email="outsider9@example.com", hire_date=date(2019, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="outsider9", password="x"),
        )
        RoleAssignment.objects.create(employee=self.outsider, role=Role.objects.get(name="employee"))

    def _open_period(self, **overrides):
        payload = {
            "employee": self.report.id, "start_date": "2026-06-01", "end_date": "2026-09-01",
        }
        payload.update(overrides)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post("/api/v1/probation-periods/", payload, format="json")
        assert response.status_code == 201, response.data
        return response.data["id"]


class OpenProbationPeriodTests(ProbationApiTestCase):
    def test_hr_admin_can_open_a_probation_period(self):
        period_id = self._open_period()
        self.assertTrue(ProbationPeriod.objects.filter(id=period_id, status="in_progress").exists())

    def test_line_manager_cannot_open_a_probation_period(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/probation-periods/",
            {"employee": self.report.id, "start_date": "2026-06-01", "end_date": "2026-09-01"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_employee_can_see_their_own_probation_period(self):
        self._open_period()
        self.client.force_authenticate(user=self.report.user)
        response = self.client.get("/api/v1/probation-periods/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_outsider_cannot_see_someone_elses_probation_period(self):
        self._open_period()
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get("/api/v1/probation-periods/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)


class ProbationReviewTests(ProbationApiTestCase):
    def test_line_manager_can_record_a_review(self):
        period_id = self._open_period()
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post("/api/v1/probation-reviews/", {
            "probation_period": period_id, "review_date": "2026-07-15", "recommendation": "continue",
            "comments": "On track.",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["reviewed_by"], self.manager.id)

    def test_outsider_cannot_record_a_review(self):
        period_id = self._open_period()
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.post("/api/v1/probation-reviews/", {
            "probation_period": period_id, "review_date": "2026-07-15", "recommendation": "continue",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProbationReview.objects.exists())

    def test_different_line_manager_cannot_review_employee_outside_their_scope(self):
        period_id = self._open_period()
        other_manager = Employee.objects.hire(
            employee_number="MGR10", first_name="Other", last_name="Manager", date_of_birth=date(1982, 1, 1),
            work_email="manager10@example.com", hire_date=date(2018, 1, 1), department=self.report.current_version.department,
            occupational_level=self.report.current_version.occupational_level,
            job_grade=self.report.current_version.job_grade, location=self.report.current_version.location,
            user=User.objects.create_user(username="manager10", password="x"),
        )
        RoleAssignment.objects.create(employee=other_manager, role=Role.objects.get(name="line_manager"))
        self.client.force_authenticate(user=other_manager.user)
        response = self.client.post("/api/v1/probation-reviews/", {
            "probation_period": period_id, "review_date": "2026-07-15", "recommendation": "continue",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProbationReview.objects.exists())

    def test_manager_cannot_set_employee_signature_fields(self):
        period_id = self._open_period()
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post("/api/v1/probation-reviews/", {
            "probation_period": period_id, "review_date": "2026-07-15", "recommendation": "continue",
            "employee_signed_at": "2026-07-15T12:00:00Z", "employee_signature_sha256": "f" * 64,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data["employee_signed_at"])
        self.assertEqual(response.data["employee_signature_sha256"], "")


class ProbationReviewSignatureTests(ProbationApiTestCase):
    def setUp(self):
        super().setUp()
        period_id = self._open_period()
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post("/api/v1/probation-reviews/", {
            "probation_period": period_id, "review_date": "2026-07-15", "recommendation": "continue",
            "comments": "On track.",
        }, format="json")
        self.review_id = response.data["id"]

    def test_employee_countersigns_with_password_and_audits_hash(self):
        self.client.force_authenticate(user=self.report.user)
        response = self.client.post(
            f"/api/v1/probation-reviews/{self.review_id}/sign/", {"password": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.data["employee_signed_at"])
        self.assertEqual(len(response.data["employee_signature_sha256"]), 64)
        self.assertTrue(AuditLogEntry.objects.filter(
            actor=self.report, entity_type="core_hr.ProbationReview", entity_id=str(self.review_id),
            action=AuditLogEntry.Action.UPDATE,
        ).exists())

    def test_wrong_password_and_third_party_are_rejected(self):
        self.client.force_authenticate(user=self.report.user)
        wrong = self.client.post(
            f"/api/v1/probation-reviews/{self.review_id}/sign/", {"password": "wrong"}, format="json"
        )
        self.assertEqual(wrong.status_code, 400)
        self.client.force_authenticate(user=self.manager.user)
        third_party = self.client.post(
            f"/api/v1/probation-reviews/{self.review_id}/sign/", {"password": "x"}, format="json"
        )
        self.assertEqual(third_party.status_code, 403)

    def test_review_cannot_be_countersigned_twice(self):
        self.client.force_authenticate(user=self.report.user)
        first = self.client.post(
            f"/api/v1/probation-reviews/{self.review_id}/sign/", {"password": "x"}, format="json"
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            f"/api/v1/probation-reviews/{self.review_id}/sign/", {"password": "x"}, format="json"
        )
        self.assertEqual(second.status_code, 409)


class ProbationOutcomeTests(ProbationApiTestCase):
    def test_hr_admin_can_confirm(self):
        period_id = self._open_period()
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/probation-periods/{period_id}/record_outcome/",
            {"status": "confirmed", "notes": "Met all expectations."}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "confirmed")
        self.assertEqual(response.data["outcome_by"], self.hr_admin.id)

    def test_line_manager_cannot_record_outcome(self):
        period_id = self._open_period()
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/probation-periods/{period_id}/record_outcome/", {"status": "confirmed"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_extending_requires_a_new_end_date(self):
        period_id = self._open_period()
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/probation-periods/{period_id}/record_outcome/", {"status": "extended"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            f"/api/v1/probation-periods/{period_id}/record_outcome/",
            {"status": "extended", "end_date": "2026-12-01"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["end_date"], "2026-12-01")

    def test_cannot_record_outcome_on_an_already_closed_period(self):
        period_id = self._open_period()
        self.client.force_authenticate(user=self.hr_admin.user)
        self.client.post(f"/api/v1/probation-periods/{period_id}/record_outcome/", {"status": "confirmed"}, format="json")
        response = self.client.post(
            f"/api/v1/probation-periods/{period_id}/record_outcome/", {"status": "terminated"}, format="json",
        )
        self.assertEqual(response.status_code, 400)


class ProbationCompletionDashboardTests(ProbationApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.hr_admin.user)

    def _confirm(self, employee, **version_overrides):
        for field, value in version_overrides.items():
            setattr(employee.current_version, field, value)
        if version_overrides:
            employee.current_version.save(update_fields=list(version_overrides))
        response = self.client.post("/api/v1/probation-periods/", {
            "employee": employee.id, "start_date": "2026-01-01", "end_date": "2026-04-01",
        }, format="json")
        period_id = response.data["id"]
        self.client.post(f"/api/v1/probation-periods/{period_id}/record_outcome/", {"status": "confirmed"}, format="json")

    def test_only_closed_periods_count_towards_the_rate(self):
        self._confirm(self.report, race="african")
        self._open_period(employee=self.outsider.id)
        response = self.client.get("/api/v1/dashboards/probation/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_closed"], 1)
        self.assertEqual(response.data["total_confirmed"], 1)
        self.assertEqual(response.data["in_progress"], 1)
        self.assertEqual(response.data["overall_completion_pct"], 100.0)

    def test_non_hr_admin_cannot_view_dashboard(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/probation/")
        self.assertEqual(response.status_code, 403)
