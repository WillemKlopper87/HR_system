from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rbac_audit.models import AuditLogEntry, Role, RoleAssignment
from rest_framework.test import APIClient

from .data_quality import run_data_quality_checks
from .models import (
    ContractRenewalDecision,
    DataQualityException,
    Department,
    Employee,
    EmployeeVersion,
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


class EmployeeSelfServiceApiTests(TestCase):
    """Sprint 15 (ESS): profile self-edit and consent-gated self-ID."""

    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin2@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin2", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.staff = Employee.objects.hire(
            employee_number="E200", first_name="Staff", last_name="Member", date_of_birth=date(1992, 1, 1),
            work_email="staff2@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="staff2", password="x"),
        )
        RoleAssignment.objects.create(employee=self.staff, role=Role.objects.get(name="employee"))

        self.outsider = Employee.objects.hire(
            employee_number="E201", first_name="Out", last_name="Sider", date_of_birth=date(1990, 1, 1),
            work_email="outsider2@example.com", hire_date=date(2019, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="outsider2", password="x"),
        )
        RoleAssignment.objects.create(employee=self.outsider, role=Role.objects.get(name="employee"))

    def test_employee_can_update_own_contact_details(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.patch(
            f"/api/v1/employees/{self.staff.id}/", {"phone": "0821234567", "personal_email": "me@personal.example"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["phone"], "0821234567")

    def test_employee_cannot_update_identity_fields(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.patch(
            f"/api/v1/employees/{self.staff.id}/", {"national_id_number": "1234567890123"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_employee_cannot_update_someone_elses_profile(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.patch(
            f"/api/v1/employees/{self.staff.id}/", {"phone": "0821234567"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_update_contact_details_on_behalf_of_employee(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.patch(
            f"/api/v1/employees/{self.staff.id}/", {"phone": "0827654321"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_self_identify_requires_consent_first(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.post(
            f"/api/v1/employees/{self.staff.id}/self_identify/", {"race": "african"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("consent", response.data["detail"].lower())

    def test_self_identify_updates_current_version_after_consent(self):
        self.client.force_authenticate(user=self.staff.user)
        consent_response = self.client.post(f"/api/v1/employees/{self.staff.id}/consent/")
        self.assertEqual(consent_response.status_code, 201)

        response = self.client.post(
            f"/api/v1/employees/{self.staff.id}/self_identify/",
            {"race": "african", "gender": "female", "disability_status": "no"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["race"], "african")
        self.assertEqual(response.data["race_source"], "self_identified")

        version = self.staff.current_version
        self.assertEqual(version.race, "african")
        self.assertEqual(version.gender, "female")
        self.assertEqual(version.race_source, "self_identified")

    def test_self_identify_rejects_invalid_choice(self):
        self.client.force_authenticate(user=self.staff.user)
        self.client.post(f"/api/v1/employees/{self.staff.id}/consent/")
        response = self.client.post(
            f"/api/v1/employees/{self.staff.id}/self_identify/", {"race": "not-a-real-race"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_employee_cannot_self_identify_for_someone_else(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.post(f"/api/v1/employees/{self.staff.id}/consent/")
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            f"/api/v1/employees/{self.staff.id}/self_identify/", {"race": "african"}, format="json"
        )
        self.assertEqual(response.status_code, 403)


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


class ContractActionApiTests(TestCase):
    """Task 3 (C1 part 2): EmployeeVersionViewSet.recommend_contract/
    decide_contract, ?fixed_term=true, and the serializer's new
    contract_end_date/contract_renewal_decision fields. Mirrors
    EmployeeViewSet.consent/self_identify's layering: RowScopePermission
    (via get_object()) gates row access first, then an inline has_role()
    check narrows further — row access alone isn't "is this specific
    person's manager" (an hr_admin has row access everywhere but must not
    recommend; a line_manager has row access to their own report but must
    not decide)."""

    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR3", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin3@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin3", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.manager = Employee.objects.hire(
            employee_number="MGR3", first_name="Line", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="manager3@example.com", hire_date=date(2018, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="manager3", password="x"),
        )
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))

        self.employee = Employee.objects.hire(
            employee_number="E300", first_name="Fixed", last_name="Termer", date_of_birth=date(1992, 1, 1),
            work_email="fixedterm3@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="fixedterm3", password="x"),
        )
        # Base "employee" role (self row-scope) — needed so
        # test_non_manager_cannot_recommend exercises the has_role()
        # narrowing rather than being rejected earlier by RowScopePermission.
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="employee"))

        # Not anyone's report and not authenticated in any test -- exists
        # purely as a target OUTSIDE self.manager's reporting chain, for
        # test_manager_outside_reporting_chain_cannot_recommend.
        self.other_employee = Employee.objects.hire(
            employee_number="E301", first_name="Some", last_name="Stranger", date_of_birth=date(1990, 1, 1),
            work_email="stranger3@example.com", hire_date=date(2019, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )

        # sysadmin/auditor: both row_scope=all (rbac_audit/migrations/
        # 0002_seed_roles.py), so RowScopePermission lets either read any
        # EmployeeVersion -- but sysadmin has I:read=False while auditor has
        # I:read=True, and neither holds hr_admin/line_manager. Used to prove
        # the two permission layers (row-scope, then role/tier) compose
        # correctly rather than either one alone deciding access.
        self.sysadmin = Employee.objects.hire(
            employee_number="SYS3", first_name="Sys", last_name="Admin", date_of_birth=date(1988, 1, 1),
            work_email="sysadmin3@example.com", hire_date=date(2016, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="sysadmin3", password="x"),
        )
        RoleAssignment.objects.create(employee=self.sysadmin, role=Role.objects.get(name="sysadmin"))

        self.auditor = Employee.objects.hire(
            employee_number="AUD3", first_name="Audrey", last_name="Auditor", date_of_birth=date(1983, 1, 1),
            work_email="auditor3@example.com", hire_date=date(2017, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="auditor3", password="x"),
        )
        RoleAssignment.objects.create(employee=self.auditor, role=Role.objects.get(name="auditor"))

        # Employee.current_version re-queries the DB on every access (it's
        # a plain property, not cached) -- fetch once into a local so all
        # three field changes land on the SAME in-memory instance before
        # the single save() call. (Setting attributes across three
        # separate `self.employee.current_version.x = ...` statements would
        # mutate three different throwaway instances and persist none of it.)
        version = self.employee.current_version
        version.employment_status = EmployeeVersion.EmploymentStatus.FIXED_TERM
        version.contract_end_date = date(2026, 12, 31)
        version.manager = self.manager
        version.save()

    def test_manager_can_recommend_for_own_report(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "recommended")

    def test_non_manager_cannot_recommend(self):
        # self.employee has row access to their OWN version (self row-scope
        # via the base "employee" role) but holds no line_manager role --
        # this must be rejected by the action's has_role() check, not by
        # RowScopePermission (which would let them through to their own row).
        self.client.force_authenticate(user=self.employee.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_decide(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "convert_permanent"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "decided")

    def test_manager_cannot_decide(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "convert_permanent"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_deciding_twice_is_400_not_500(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        # Captured ONCE: decide_contract's convert_permanent path closes this
        # version and opens a new "current" one (apply_lifecycle_event), so
        # re-reading self.employee.current_version.id after the first POST
        # would silently point the second POST at the NEW (undecided)
        # version instead of re-testing the SAME decision -- masking the
        # very re-decide case this test exists to cover.
        version_id = self.employee.current_version.id
        first = self.client.post(
            f"/api/v1/employee-versions/{version_id}/decide_contract/",
            {"action": "convert_permanent"}, format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        response = self.client.post(
            f"/api/v1/employee-versions/{version_id}/decide_contract/",
            {"action": "let_lapse"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_fixed_term_filter(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/employee-versions/?fixed_term=true&current=true")
        self.assertEqual(response.status_code, 200)
        returned_ids = (
            {v["id"] for v in response.data["results"]}
            if "results" in response.data
            else {v["id"] for v in response.data}
        )
        self.assertIn(self.employee.current_version.id, returned_ids)
        # self.manager is still PERMANENT (default from hire()) -- proves
        # this actually filters rather than ?fixed_term=true being a no-op
        # that ?current=true alone would satisfy anyway.
        self.assertNotIn(self.manager.current_version.id, returned_ids)

    def test_serializer_includes_null_decision_before_any_action(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/employee-versions/{self.employee.current_version.id}/")
        self.assertIsNone(response.data["contract_renewal_decision"])

    def test_manager_outside_reporting_chain_cannot_recommend(self):
        # self.other_employee is NOT self.manager's report -- get_object()
        # runs RowScopePermission.has_object_permission() before this
        # action's body (and its has_role() check) ever executes, so this
        # must 403 at the row-scope layer, distinct from
        # test_non_manager_cannot_recommend's has_role()-layer 403.
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.other_employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_auditor_all_scope_row_access_cannot_decide(self):
        # auditor holds an ALL row-scope role, so get_object() succeeds --
        # RowScopePermission alone would let this through. It must still be
        # rejected by decide_contract's has_role(actor, "hr_admin") check:
        # broad row access is not the same as holding the specific role
        # this action requires. Proves the two layers compose (row access
        # without the right role is still refused; see
        # test_manager_outside_reporting_chain_cannot_recommend for the
        # opposite composition -- the right role without row access).
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "convert_permanent"}, format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_line_manager_sees_decision_comments_but_sysadmin_does_not(self):
        # Finding from task review: ContractRenewalDecisionSerializer is a
        # plain ModelSerializer (not TieredModelSerializer), so per-field
        # tiering never applies inside it -- the gate has to be the OUTER
        # contract_renewal_decision field on EmployeeVersionSerializer,
        # registered INTERNAL in rbac_audit/tiers.py. Seeded role matrix
        # (rbac_audit/migrations/0002_seed_roles.py): line_manager/hr_admin/
        # auditor all have I:read=True (so the design spec's three intended
        # consumers are unaffected); sysadmin has I:read=False (P:read is
        # also False, but PUBLIC-tier fields bypass the grant check
        # entirely per can_access_tier_for_target, so only INTERNAL-and-up
        # fields are actually at stake here) despite row_scope=all putting
        # every record within RowScopePermission's reach -- exactly the
        # over-exposure this fix closes.
        self.client.force_authenticate(user=self.hr_admin.user)
        version_id = self.employee.current_version.id
        decide_response = self.client.post(
            f"/api/v1/employee-versions/{version_id}/decide_contract/",
            {"action": "convert_permanent", "comment": "Approved after performance review."}, format="json",
        )
        self.assertEqual(decide_response.status_code, 200, decide_response.data)

        # Intended consumer: the report's own line_manager (own_team
        # row-scope) sees the nested decision, comment included.
        self.client.force_authenticate(user=self.manager.user)
        manager_view = self.client.get(f"/api/v1/employee-versions/{version_id}/")
        self.assertEqual(manager_view.status_code, 200, manager_view.data)
        self.assertIsNotNone(manager_view.data["contract_renewal_decision"])
        self.assertEqual(
            manager_view.data["contract_renewal_decision"]["decided_comment"],
            "Approved after performance review.",
        )

        # sysadmin: row_scope=all so the record itself is reachable (200),
        # but I:read=False means the whole INTERNAL-tier
        # contract_renewal_decision field must be stripped from the
        # response entirely -- not merely its comment sub-field.
        self.client.force_authenticate(user=self.sysadmin.user)
        sysadmin_view = self.client.get(f"/api/v1/employee-versions/{version_id}/")
        self.assertEqual(sysadmin_view.status_code, 200, sysadmin_view.data)
        self.assertNotIn("contract_renewal_decision", sysadmin_view.data)

    def test_employee_cannot_see_own_decision_but_can_see_own_contract_end_date(self):
        # Design spec Sec2, explicitly out of scope: "the employee does not
        # see or participate in this workflow -- only the outcome (their
        # employment record changing) is visible to them." contract_end_date
        # IS that outcome and must stay visible; the decision object
        # (including its free-text manager/HR comments) must not, even
        # though tier-wise the base "employee" role holds I:read=True on
        # its own row -- this is a row-relational gate (is the requester
        # the record's own subject with no separate entitlement over it),
        # not a tier one, per the second review round on this task.
        self.client.force_authenticate(user=self.hr_admin.user)
        version_id = self.employee.current_version.id
        decide_response = self.client.post(
            f"/api/v1/employee-versions/{version_id}/decide_contract/",
            {"action": "convert_permanent", "comment": "Approved after performance review."}, format="json",
        )
        self.assertEqual(decide_response.status_code, 200, decide_response.data)

        self.client.force_authenticate(user=self.employee.user)
        self_view = self.client.get(f"/api/v1/employee-versions/{version_id}/")
        self.assertEqual(self_view.status_code, 200, self_view.data)
        self.assertIsNone(self_view.data["contract_renewal_decision"])
        self.assertEqual(self_view.data["contract_end_date"], "2026-12-31")

    def test_line_manager_and_hr_admin_still_see_decision_for_that_same_employee(self):
        # Pins the other direction of the fix above: hiding the decision
        # from the SUBJECT must not collapse into hiding it from everyone
        # -- the report's own line_manager and hr_admin (the design spec's
        # actual intended consumers) still see it exactly as before.
        self.client.force_authenticate(user=self.hr_admin.user)
        version_id = self.employee.current_version.id
        decide_response = self.client.post(
            f"/api/v1/employee-versions/{version_id}/decide_contract/",
            {"action": "convert_permanent", "comment": "Approved after performance review."}, format="json",
        )
        self.assertEqual(decide_response.status_code, 200, decide_response.data)

        self.client.force_authenticate(user=self.manager.user)
        manager_view = self.client.get(f"/api/v1/employee-versions/{version_id}/")
        self.assertEqual(manager_view.status_code, 200, manager_view.data)
        self.assertIsNotNone(manager_view.data["contract_renewal_decision"])

        self.client.force_authenticate(user=self.hr_admin.user)
        hr_admin_view = self.client.get(f"/api/v1/employee-versions/{version_id}/")
        self.assertEqual(hr_admin_view.status_code, 200, hr_admin_view.data)
        self.assertIsNotNone(hr_admin_view.data["contract_renewal_decision"])

    def test_hr_admin_viewing_own_record_still_sees_decision_via_hr_admin_entitlement(self):
        # "Someone who happens to be both" (coordinator's framing): an
        # hr_admin who is also the subject of a decision must still see it,
        # via their hr_admin entitlement -- the subject-is-requester check
        # must key on "holds a separate entitlement", not "is this my own
        # row", or this case would wrongly hide it too.
        self.client.force_authenticate(user=self.hr_admin.user)
        own_version = self.hr_admin.current_version
        own_version.employment_status = EmployeeVersion.EmploymentStatus.FIXED_TERM
        own_version.contract_end_date = date(2026, 6, 30)
        own_version.save()
        version_id = own_version.id

        decide_response = self.client.post(
            f"/api/v1/employee-versions/{version_id}/decide_contract/",
            {"action": "convert_permanent", "comment": "Self-approved, no conflict of interest here."},
            format="json",
        )
        self.assertEqual(decide_response.status_code, 200, decide_response.data)

        self_view = self.client.get(f"/api/v1/employee-versions/{version_id}/")
        self.assertEqual(self_view.status_code, 200, self_view.data)
        self.assertIsNotNone(self_view.data["contract_renewal_decision"])

    def test_second_same_day_decide_on_resulting_version_is_400_not_500(self):
        # RENEW/CONVERT_PERMANENT close the current version today and open a
        # NEW one via apply_lifecycle_event -- that new version's valid_from
        # is also today. Deciding *that* new version again the same day
        # used to hit apply_lifecycle_event's own
        # "effective_date <= current.valid_from" guard, which raises a bare
        # ValueError decide_contract_action's `except ContractDecisionError`
        # doesn't catch -- an unhandled 500. task-3-report.md already
        # flagged this exact failure mode by name (in the different but
        # related test_deciding_twice_is_400_not_500 scenario: re-deciding
        # the SAME version) and routed the test around it rather than
        # fixing the underlying gap; this test targets the fix directly.
        self.client.force_authenticate(user=self.hr_admin.user)
        first_version_id = self.employee.current_version.id
        first = self.client.post(
            f"/api/v1/employee-versions/{first_version_id}/decide_contract/",
            {"action": "renew", "end_date": "2027-06-30", "comment": "First renewal."}, format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        resulting_version_id = first.data["resulting_employee_version"]
        self.assertIsNotNone(resulting_version_id)

        second = self.client.post(
            f"/api/v1/employee-versions/{resulting_version_id}/decide_contract/",
            {"action": "renew", "end_date": "2027-12-31", "comment": "Second, same-day decide."}, format="json",
        )
        self.assertEqual(second.status_code, 400, second.data)

        # The first decision's effects must remain intact -- not rolled
        # back or corrupted by the second (rejected) attempt's transaction.
        current = self.employee.current_version
        self.assertEqual(current.id, resulting_version_id)
        self.assertEqual(current.contract_end_date, date(2027, 6, 30))
        first_decision = EmployeeVersion.objects.get(id=first_version_id).contract_renewal_decision
        self.assertEqual(first_decision.status, "decided")
        self.assertEqual(first_decision.decided_end_date, date(2027, 6, 30))

    def test_unparseable_end_date_is_400_not_500_on_recommend(self):
        # Final-review finding 1: request.data["end_date"] used to reach
        # ContractRenewalDecision.objects.create() unvalidated, where
        # DateField.get_prep_value() raises django.core.exceptions
        # .ValidationError -- an Exception, NOT a ValueError, so
        # contracts.py's `except ValueError` never caught it and DRF's
        # default handler (no EXCEPTION_HANDLER override in settings.py)
        # never translated it: an unhandled 500. Same defect class
        # rbac_audit.drf.int_query_param's docstring hardened the read
        # layer against.
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "tomorrow"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("end_date", response.data)

    def test_unparseable_end_date_is_400_not_500_on_decide(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "renew", "end_date": "tomorrow"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("end_date", response.data)

    def test_unknown_action_is_400_with_field_errors(self):
        # The hand-rolled `action not in Action.values` check is gone --
        # the input serializer's ChoiceField reports it instead, keeping
        # one validation path rather than two.
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "explode"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("action", response.data)

    def test_past_end_date_is_rejected_on_recommend(self):
        # Spec §4: the new end_date "must be after the version's current
        # contract_end_date". Without this a fat-fingered past date
        # creates a FIXED_TERM version whose contract already expired and
        # which nothing ever surfaces again (contract_reminders.py can
        # never match a negative days_remaining; the data-quality check
        # only fires on NULL).
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2017-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(
            ContractRenewalDecision.objects.filter(
                employee_version=self.employee.current_version
            ).exists()
        )

    def test_end_date_equal_to_current_end_date_is_rejected_on_decide(self):
        # "after", not "on or after" -- re-stamping the same date is not a
        # renewal, it just burns the one decision this contract gets.
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "renew", "end_date": "2026-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_past_end_date_rejected_when_version_has_no_current_end_date(self):
        # Spec §7 leaves pre-existing fixed-term employees un-backfilled
        # (contract_end_date IS NULL, flagged by MISSING_CONTRACT_END_DATE),
        # so these endpoints are reachable with nothing to order against.
        # The ordering rule falls back to today rather than waving the
        # renewal through -- the "already-expired fixed-term version"
        # black hole is identical either way.
        version = self.employee.current_version
        version.contract_end_date = None
        version.save(update_fields=["contract_end_date"])
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{version.id}/decide_contract/",
            {"action": "renew", "end_date": "2017-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_future_end_date_still_renews(self):
        # The positive control for the two rejection tests above: a
        # genuinely later date is still accepted and still executes.
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/decide_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.employee.current_version.contract_end_date, date(2027, 12, 31))

    def _promote_to_close_current_version(self):
        """Closes self.employee's current version and opens a successor,
        returning the now-historical version's id — the shape
        apply_lifecycle_event leaves behind after ANY version change.

        Dated yesterday, not today, deliberately: a successor whose
        valid_from is today would make apply_lifecycle_event's own
        "effective_date must be after valid_from" guard reject a
        same-day decide anyway, so the test would pass without the
        current-version guard actually doing anything."""
        closed_id = self.employee.current_version.id
        self.employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.PROMOTION,
            effective_date=timezone.localdate() - timedelta(days=1),
        )
        return closed_id

    def _make_permanent_report(self):
        """A PERMANENT employee reporting to self.manager — the target the
        fixed-term guard exists to protect."""
        dept = self.employee.current_version.department
        permanent = Employee.objects.hire(
            employee_number="E302", first_name="Perma", last_name="Nent",
            date_of_birth=date(1991, 1, 1), work_email="permanent3@example.com",
            hire_date=date(2020, 1, 1), department=dept,
            occupational_level=self.employee.current_version.occupational_level,
            job_grade=self.employee.current_version.job_grade,
            location=self.employee.current_version.location,
        )
        version = permanent.current_version
        version.manager = self.manager
        version.save(update_fields=["manager"])
        return permanent

    def test_cannot_recommend_on_a_permanent_version(self):
        # Final-review finding 3. Neither service function checked
        # employment_status, so the FIXED_TERM scoping the spec assumes
        # throughout (§3.1/§5/§7/§9) existed nowhere in code. Recommending
        # a renewal on a PERMANENT version is meaningless.
        permanent = self._make_permanent_report()
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{permanent.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(ContractRenewalDecision.objects.filter(
            employee_version=permanent.current_version).exists())

    def test_cannot_let_lapse_a_permanent_employee(self):
        # The severe case: these two actions are the only API-reachable
        # callers of apply_lifecycle_event in the entire backend, so
        # without this guard an hr_admin could terminate a PERMANENT
        # employee with termination_reason=CONTRACT_END — corrupt EEA2
        # statutory workforce-movement data, from a UI-unreachable but
        # fully API-reachable path.
        permanent = self._make_permanent_report()
        version_id = permanent.current_version.id
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{version_id}/decide_contract/",
            {"action": "let_lapse"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(EmploymentEvent.objects.filter(
            employee=permanent, event_type=EmploymentEvent.EventType.TERMINATION).exists())
        # Still employed, on the same still-open version.
        self.assertIsNotNone(permanent.current_version)
        self.assertEqual(permanent.current_version.id, version_id)
        self.assertFalse(ContractRenewalDecision.objects.filter(employee_version_id=version_id).exists())

    def test_cannot_recommend_on_a_historical_closed_version(self):
        closed_id = self._promote_to_close_current_version()
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{closed_id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(ContractRenewalDecision.objects.filter(employee_version_id=closed_id).exists())

    def test_cannot_decide_on_a_historical_closed_version(self):
        # apply_lifecycle_event always acts on the employee's CURRENT open
        # version, while the decision row is written against the
        # employee_version argument — so deciding on a closed V1 recorded
        # the decision on V1 while the event closed V2: one act split
        # across two rows of the audit trail.
        closed_id = self._promote_to_close_current_version()
        current_id = self.employee.current_version.id
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{closed_id}/decide_contract/",
            {"action": "convert_permanent"}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(ContractRenewalDecision.objects.filter(employee_version_id=closed_id).exists())
        # The current version must be untouched — not closed by an event
        # recorded against a different row.
        self.assertEqual(self.employee.current_version.id, current_id)

    def test_all_scope_role_holder_who_is_also_a_line_manager_cannot_recommend_outside_their_chain(self):
        # Final-review finding 5. has_role() is scope-blind and
        # RowScopePermission grants object access if ANY active role covers
        # the target, so `has_role(actor, "line_manager")` alone let an
        # actor holding line_manager PLUS any row_scope=all role recommend
        # for every employee in the organisation — contradicting spec §6
        # and re-opening the cross-role composition hazard
        # can_access_tier_for_target exists to close. Not hypothetical:
        # RBAC-Roles.md derives line_manager from having direct reports, so
        # in production an hr_head/ee_manager with reports holds both.
        RoleAssignment.objects.create(employee=self.auditor, role=Role.objects.get(name="line_manager"))
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(ContractRenewalDecision.objects.filter(
            employee_version=self.employee.current_version).exists())

    def test_line_manager_holding_an_extra_all_scope_role_can_still_recommend_for_own_report(self):
        # The other direction of the same fix: narrowing to the reporting
        # chain must not strip a genuine manager of their own reports just
        # because they also hold a wider role.
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="auditor"))
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            f"/api/v1/employee-versions/{self.employee.current_version.id}/recommend_contract/",
            {"action": "renew", "end_date": "2027-12-31"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
