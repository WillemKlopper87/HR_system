from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.models import AuditLogEntry, Role, RoleAssignment
from rest_framework.test import APIClient

from .data_quality import run_data_quality_checks
from .models import (
    DataQualityException,
    Department,
    Employee,
    EmploymentEvent,
    JobGrade,
    Location,
    OccupationalLevel,
)

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class EmployeeApiTests(TestCase):
    """Sprint 3: EmployeeViewSet reuses the exact RBAC pattern proven by
    EmployeeVersionViewSet in Sprint 2 — this checks that reuse actually
    holds for a second model, not the underlying permission logic itself
    (rbac_audit's own suite already covers that)."""

    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.staff = Employee.objects.hire(
            employee_number="E100", first_name="Staff", last_name="Member", date_of_birth=date(1992, 1, 1),
            work_email="staff@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="staff", password="x"),
        )
        # hire() grants no roles (role provisioning is a separate concern —
        # see rbac_audit's own tests); self-scope access needs it explicit.
        RoleAssignment.objects.create(employee=self.staff, role=Role.objects.get(name="employee"))

    def test_hr_admin_sees_all_employees(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/employees/")
        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.hr_admin.id, returned_ids)
        self.assertIn(self.staff.id, returned_ids)

    def test_self_scope_employee_sees_only_self_in_list(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.get("/api/v1/employees/")
        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(returned_ids, {self.staff.id})

    def test_self_scope_employee_can_read_own_detail(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.get(f"/api/v1/employees/{self.staff.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["employee_number"], "E100")

    def test_self_scope_employee_blocked_from_colleague_detail(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.get(f"/api/v1/employees/{self.hr_admin.id}/")
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/v1/employees/")
        self.assertEqual(response.status_code, 403)

    def test_search_filters_by_name(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/employees/?search=Staff")
        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(returned_ids, {self.staff.id})


class EmployeeVersionQueryParamTests(TestCase):
    """Sprint 3 additions to the Sprint 2 endpoint: ?employee= and
    ?current=true, used by the detail page's history panel and the list
    view respectively."""

    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()
        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))
        self.employee = Employee.objects.hire(
            employee_number="E100", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="e100@example.com", hire_date=date(2020, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )
        self.employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.TRANSFER, effective_date=date(2023, 1, 1), department=dept,
        )

    def test_employee_filter_returns_full_history(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/employee-versions/?employee={self.employee.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)

    def test_current_filter_returns_only_open_version(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/employee-versions/?employee={self.employee.id}&current=true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNone(response.data["results"][0]["valid_to"])


class OrgStructureApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()
        self.dept = dept

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.staff = Employee.objects.hire(
            employee_number="E100", first_name="Staff", last_name="Member", date_of_birth=date(1992, 1, 1),
            work_email="staff@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="staff", password="x"),
        )

    def test_any_authenticated_employee_can_read_departments(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.get("/api/v1/departments/")
        self.assertEqual(response.status_code, 200)

    def test_non_hr_admin_cannot_create_department(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.post("/api/v1/departments/", {"name": "New Dept", "code": "NEW"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_create_department(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post("/api/v1/departments/", {"name": "New Dept", "code": "NEW"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Department.objects.filter(code="NEW").exists())

    def test_hr_admin_cannot_delete_department_in_use(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.delete(f"/api/v1/departments/{self.dept.id}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Department.objects.filter(id=self.dept.id).exists())

    def test_occupational_levels_are_read_only(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        level = OccupationalLevel.objects.first()
        response = self.client.patch(f"/api/v1/occupational-levels/{level.id}/", {"name": "Changed"}, format="json")
        self.assertEqual(response.status_code, 405)


class DataQualityExceptionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.staff = Employee.objects.hire(
            employee_number="E100", first_name="No", last_name="Grade", date_of_birth=date(1992, 1, 1),
            work_email="nograde@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=None, location=location,
            user=User.objects.create_user(username="staff", password="x"),
        )
        run_data_quality_checks()
        self.exception = DataQualityException.objects.get(
            employee=self.staff, exception_type=DataQualityException.ExceptionType.MISSING_GRADE
        )

    def test_non_hr_admin_cannot_view_queue(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.get("/api/v1/data-quality-exceptions/")
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_sees_open_exceptions(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/data-quality-exceptions/")
        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.exception.id, returned_ids)

    def test_resolve_closes_exception_and_is_audited(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/data-quality-exceptions/{self.exception.id}/resolve/")
        self.assertEqual(response.status_code, 200)
        self.exception.refresh_from_db()
        self.assertIsNotNone(self.exception.resolved_at)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                entity_type="core_hr.DataQualityException", entity_id=str(self.exception.id),
                action=AuditLogEntry.Action.UPDATE,
            ).exists()
        )

    def test_resolving_twice_is_rejected(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        self.client.post(f"/api/v1/data-quality-exceptions/{self.exception.id}/resolve/")
        response = self.client.post(f"/api/v1/data-quality-exceptions/{self.exception.id}/resolve/")
        self.assertEqual(response.status_code, 400)

    def test_run_checks_returns_open_count(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post("/api/v1/data-quality-exceptions/run_checks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["open_exceptions"],
            DataQualityException.objects.filter(resolved_at__isnull=True).count(),
        )

    def test_non_hr_admin_cannot_trigger_run_checks(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.post("/api/v1/data-quality-exceptions/run_checks/")
        self.assertEqual(response.status_code, 403)


class HeadcountDashboardApiTests(TestCase):
    """Gap C6 / RBAC-Roles.md standing rule 1: demographic breakdowns must
    suppress cells with n < 5 for any role without Sensitive-tier read."""

    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2015, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="hradmin", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.manager = Employee.objects.hire(
            employee_number="MGR", first_name="Line", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="manager@example.com", hire_date=date(2018, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="manager", password="x"),
        )
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))

        # 3 African employees — below the n<5 suppression threshold.
        for i in range(3):
            Employee.objects.hire(
                employee_number=f"E10{i}", first_name="Emp", last_name=str(i), date_of_birth=date(1990, 1, 1),
                work_email=f"emp{i}@example.com", hire_date=date(2022, 1, 1), department=self.dept,
                occupational_level=self.level, job_grade=self.grade, location=self.location,
                race="african",
            )

    def test_hr_admin_sees_unsuppressed_counts(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/headcount/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["small_cell_suppression_applied"])
        african_row = next(r for r in response.data["by_race"] if r["key"] == "african")
        self.assertEqual(african_row["count"], 3)
        self.assertFalse(african_row["suppressed"])

    def test_line_manager_sees_suppressed_small_cells(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/headcount/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["small_cell_suppression_applied"])
        african_row = next(r for r in response.data["by_race"] if r["key"] == "african")
        self.assertTrue(african_row["suppressed"])
        self.assertEqual(african_row["count"], "<5")

    def test_department_breakdown_is_never_suppressed(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/headcount/")
        dept_row = next(r for r in response.data["by_department"] if r["key"] == self.dept.name)
        self.assertFalse(dept_row["suppressed"])
        self.assertIsInstance(dept_row["count"], int)

    def test_total_headcount_matches_current_versions(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/headcount/")
        self.assertEqual(response.data["total_headcount"], 5)  # hr_admin + manager + 3 african
