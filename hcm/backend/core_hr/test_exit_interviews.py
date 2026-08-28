from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import EmploymentChange, ExitInterview, ProbationPeriod

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


class ExitInterviewRelationshipValidationTests(ExitInterviewApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.hr_admin.user)
        self.change = EmploymentChange.objects.create(
            employee=self.leaver, change_type=EmploymentChange.ChangeType.RESIGNATION,
            effective_date=date(2026, 8, 1), reason="Resigning for a new opportunity.",
            proposed_by=self.hr_admin, proposed_at=timezone.now(),
        )
        self.other_leaver = Employee.objects.hire(
            employee_number="E801", first_name="Another", last_name="Leaver", date_of_birth=date(1988, 1, 1),
            work_email="another8@example.com", hire_date=date(2019, 1, 1), department=self.leaver.current_version.department,
            occupational_level=self.leaver.current_version.occupational_level,
            job_grade=self.leaver.current_version.job_grade, location=self.leaver.current_version.location,
        )

    def test_employment_change_must_belong_to_the_selected_employee(self):
        response = self.client.post("/api/v1/exit-interviews/", {
            "employee": self.other_leaver.id, "employment_change": self.change.id,
            "interview_date": "2026-08-01", "primary_reason": "career_growth",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("employment_change", response.data)

    def test_probation_period_must_belong_to_the_selected_employee(self):
        period = ProbationPeriod.objects.create(
            employee=self.leaver, start_date=date(2026, 1, 1), end_date=date(2026, 4, 1),
            status=ProbationPeriod.Status.TERMINATED,
        )
        response = self.client.post("/api/v1/exit-interviews/", {
            "employee": self.other_leaver.id, "probation_period": period.id,
            "interview_date": "2026-04-01", "primary_reason": "role_fit",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("probation_period", response.data)

    def test_both_triggers_at_once_is_rejected(self):
        period = ProbationPeriod.objects.create(
            employee=self.leaver, start_date=date(2026, 1, 1), end_date=date(2026, 4, 1),
            status=ProbationPeriod.Status.TERMINATED,
        )
        response = self.client.post("/api/v1/exit-interviews/", {
            "employee": self.leaver.id, "employment_change": self.change.id, "probation_period": period.id,
            "interview_date": "2026-08-01", "primary_reason": "role_fit",
        }, format="json")
        self.assertEqual(response.status_code, 400)

    def test_a_single_matching_trigger_is_accepted(self):
        response = self.client.post("/api/v1/exit-interviews/", {
            "employee": self.leaver.id, "employment_change": self.change.id,
            "interview_date": "2026-08-01", "primary_reason": "career_growth",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)


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

    def test_breakdown_uses_the_version_as_at_the_interview_date_not_today(self):
        """A demographic correction made AFTER the interview must not
        retroactively move the leaver into a different group -- the
        regulatory review's "historical employee versions" P1 finding."""
        version1 = self.leaver.current_version
        version1.valid_to = date(2026, 6, 1)
        version1.save(update_fields=["valid_to"])
        version2_fields = {
            f: getattr(version1, f) for f in [
                "department", "job_title", "occupational_level", "job_grade", "manager",
                "employment_status", "citizenship_status", "location", "position", "contract_end_date",
                "gender", "disability_status", "disability_detail", "race_source", "disability_source",
            ]
        }
        EmployeeVersion.objects.create(
            employee=self.leaver, valid_from=date(2026, 6, 1), valid_to=None,
            race="coloured", **version2_fields,
        )
        ExitInterview.objects.create(
            employee=self.leaver, interview_date=date(2026, 5, 1), conducted_by=self.hr_admin,
            primary_reason=ExitInterview.Reason.CAREER_GROWTH,
        )
        response = self.client.get("/api/v1/dashboards/exit-interviews/")
        self.assertEqual(response.status_code, 200)
        keys = {row["key"] for row in response.data["by_race"]}
        self.assertIn("african", keys)
        self.assertNotIn("coloured", keys)
