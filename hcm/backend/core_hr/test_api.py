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
