from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class OverviewDashboardTests(TestCase):
    """core_hr.views_overview.overview_dashboard -- the role-adaptive
    landing dashboard (Wireframe all features spec(4), Style A). One
    endpoint, three payloads, bucketed by the viewer's widest active
    row-scope grant rather than a hardcoded role list."""

    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.today = timezone.localdate()

        self.hr_admin = Employee.objects.hire(
            employee_number="OV001", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="ov-hradmin@example.com", hire_date=date(2015, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="ov-hradmin", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.manager = Employee.objects.hire(
            employee_number="OV002", first_name="Line", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="ov-manager@example.com", hire_date=date(2018, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="ov-manager", password="x"),
        )
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))

        self.report = Employee.objects.hire(
            employee_number="OV003", first_name="Direct", last_name="Report", date_of_birth=date(1992, 1, 1),
            work_email="ov-report@example.com", hire_date=date(2021, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="ov-report", password="x"),
        )
        RoleAssignment.objects.create(employee=self.report, role=Role.objects.get(name="employee"))

        self.stranger = Employee.objects.hire(
            employee_number="OV004", first_name="Some", last_name="Stranger", date_of_birth=date(1990, 1, 1),
            work_email="ov-stranger@example.com", hire_date=date(2019, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="ov-stranger", password="x"),
        )
        RoleAssignment.objects.create(employee=self.stranger, role=Role.objects.get(name="employee"))

        # Not in self.manager's reporting chain -- proves the line_manager
        # queue is genuinely row-scoped, not just role-scoped.
        report_version = self.report.current_version
        report_version.manager = self.manager
        report_version.employment_status = EmployeeVersion.EmploymentStatus.FIXED_TERM
        report_version.contract_end_date = self.today + timedelta(days=10)
        report_version.save()

        stranger_version = self.stranger.current_version
        stranger_version.employment_status = EmployeeVersion.EmploymentStatus.FIXED_TERM
        stranger_version.contract_end_date = self.today + timedelta(days=10)
        stranger_version.save()

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/v1/dashboards/overview/")
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_gets_the_org_wide_bucket(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/overview/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["row_scope"], "hr_admin")
        self.assertIn("kpis", response.data)
        self.assertTrue(len(response.data["kpis"]) > 0)
        self.assertIn("departments", response.data)
        self.assertIn("occupational_levels", response.data)
        self.assertIn("recruitment_funnel", response.data)
        self.assertIn("training_compliance", response.data)
        self.assertIn("policy_acknowledgment", response.data)

    def test_line_manager_gets_own_team_bucket_scoped_to_their_reports(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/overview/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["row_scope"], "line_manager")
        # own_team row-scope covers direct reports, not the manager's own
        # row (that comes from the separate base "employee" role's self
        # scope, which this fixture deliberately doesn't hold -- same
        # shape as core_hr/test_api.py's own manager fixture) -- one
        # direct report, not the stranger, and not org-wide.
        team_kpi = next(k for k in response.data["kpis"] if k["label"] == "Team headcount")
        self.assertEqual(team_kpi["value"], "1")
        # hr_admin/line_manager both see a departments breakdown, but
        # line_manager's is unaffected here -- absence of the org-wide-only
        # widgets is the real assertion.
        self.assertNotIn("occupational_levels", response.data)
        self.assertNotIn("training_compliance", response.data)

    def test_line_manager_departments_breakdown_is_row_scoped_not_org_wide(self):
        """A real bug caught while building this: the departments
        breakdown originally queried EmployeeVersion.objects.current()
        unscoped for every bucket, which would have leaked an org-wide
        department headcount to a line_manager. self.stranger sits in the
        same department as self.report but isn't self.manager's report --
        if scoping were broken, the department count here would be 2, not 1."""
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/overview/")
        eng_row = next(row for row in response.data["departments"] if row["key"] == self.dept.name)
        self.assertEqual(eng_row["count"], 1)

    def test_employee_gets_self_scope_bucket(self):
        self.client.force_authenticate(user=self.report.user)
        response = self.client.get("/api/v1/dashboards/overview/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["row_scope"], "employee")
        self.assertNotIn("departments", response.data)
        self.assertNotIn("occupational_levels", response.data)

    def test_line_manager_queue_only_shows_their_own_reporting_chain(self):
        """The stranger's contract is also expiring soon, but the stranger
        isn't self.manager's report -- if row_scoped_queryset were wired
        wrong (or skipped), the stranger would leak into the manager's
        queue."""
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/overview/")
        titles = " ".join(item["title"] for item in response.data["queue"])
        self.assertIn("Direct Report", titles)
        self.assertNotIn("Stranger", titles)

    def test_hr_admin_sees_contract_renewal_awaiting_their_decision(self):
        # The manager recommends a renewal for their report; that should
        # surface in hr_admin's queue as "awaiting HR decision" and
        # disappear from the manager's own "awaiting my recommendation"
        # queue, since it's no longer unrecommended.
        self.client.force_authenticate(user=self.manager.user)
        recommend = self.client.post(
            f"/api/v1/employee-versions/{self.report.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": str(self.today + timedelta(days=400))}, format="json",
        )
        self.assertEqual(recommend.status_code, 200, recommend.data)

        manager_response = self.client.get("/api/v1/dashboards/overview/")
        manager_titles = " ".join(item["title"] for item in manager_response.data["queue"])
        self.assertNotIn("Recommend contract renewal", manager_titles)

        self.client.force_authenticate(user=self.hr_admin.user)
        hr_response = self.client.get("/api/v1/dashboards/overview/")
        hr_titles = " ".join(item["title"] for item in hr_response.data["queue"])
        self.assertIn("Decide contract renewal", hr_titles)
        self.assertIn("Direct Report", hr_titles)

    def test_employee_queue_lists_outstanding_policy_acknowledgment(self):
        from policies.models import Policy

        Policy.objects.create(
            code="remote-work-policy", title="Remote Work Policy", category=Policy.Category.REMOTE_WORK,
            version=1, status=Policy.Status.PUBLISHED, body="Work from anywhere.",
            published_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.report.user)
        response = self.client.get("/api/v1/dashboards/overview/")
        titles = " ".join(item["title"] for item in response.data["queue"])
        self.assertIn("Acknowledge Remote Work Policy", titles)
        policies_kpi = next(k for k in response.data["kpis"] if k["label"] == "Policies to acknowledge")
        self.assertEqual(policies_kpi["value"], "1")

    def test_accounting_officer_gets_hr_admin_bucket_but_suppressed_matrix(self):
        """accounting_officer holds row_scope=all (so lands in the same
        bucket as hr_admin) but no standing Sensitive-tier grant
        (RBAC-Roles.md) -- the occupational-level totals should come back
        small-cell-suppressed for them, unlike for hr_admin."""
        officer = Employee.objects.hire(
            employee_number="OV005", first_name="Officer", last_name="Accounting", date_of_birth=date(1979, 1, 1),
            work_email="ov-officer@example.com", hire_date=date(2014, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="ov-officer", password="x"),
        )
        RoleAssignment.objects.create(employee=officer, role=Role.objects.get(name="accounting_officer"))

        self.client.force_authenticate(user=officer.user)
        response = self.client.get("/api/v1/dashboards/overview/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["row_scope"], "hr_admin")
        self.assertTrue(response.data["small_cell_suppression_applied"])

        self.client.force_authenticate(user=self.hr_admin.user)
        hr_response = self.client.get("/api/v1/dashboards/overview/")
        self.assertFalse(hr_response.data["small_cell_suppression_applied"])
