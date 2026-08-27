from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import ExitInterview

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class ExitInterviewApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR8", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin8@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin8", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.manager = Employee.objects.hire(
            employee_number="MGR8", first_name="Line", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="manager8@example.com", hire_date=date(2018, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="manager8", password="x"),
        )
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))

        self.leaver = Employee.objects.hire(
            employee_number="E800", first_name="Leaving", last_name="Soon", date_of_birth=date(1990, 1, 1),
            work_email="leaver8@example.com", hire_date=date(2020, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location, race="african", gender="female",
        )


class ExitInterviewPermissionTests(ExitInterviewApiTestCase):
    def test_hr_admin_can_record_an_interview(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post("/api/v1/exit-interviews/", {
            "employee": self.leaver.id, "interview_date": "2026-08-01", "primary_reason": "career_growth",
            "comments": "Leaving for a bigger role elsewhere.",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["conducted_by"], self.hr_admin.id)

    def test_line_manager_cannot_record_an_interview(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/exit-interviews/")
        self.assertEqual(response.status_code, 403)

    def test_leaver_themselves_cannot_view_exit_interviews(self):
        user = User.objects.create_user(username="leaver8", password="x")
        self.leaver.user = user
        self.leaver.save(update_fields=["user"])
        self.client.force_authenticate(user=user)
        response = self.client.get("/api/v1/exit-interviews/")
        self.assertEqual(response.status_code, 403)


class ExitInterviewDashboardTests(ExitInterviewApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.hr_admin.user)

    def test_breakdown_by_race_and_reason(self):
        ExitInterview.objects.create(
            employee=self.leaver, interview_date=date(2026, 8, 1), conducted_by=self.hr_admin,
            primary_reason=ExitInterview.Reason.CAREER_GROWTH,
        )
        response = self.client.get("/api/v1/dashboards/exit-interviews/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_interviews"], 1)
        african_row = next(r for r in response.data["by_race"] if r["key"] == "african")
        self.assertEqual(african_row["total"], 1)

    def test_non_hr_admin_cannot_view_dashboard(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/exit-interviews/")
        self.assertEqual(response.status_code, 403)
