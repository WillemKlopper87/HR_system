from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel

from .consent import has_active_consent, record_consent, withdraw_consent
from .models import AuditLogEntry, ConsentRecord, Role, RoleAssignment
from .permissions import can_access_tier, has_row_access, is_in_reporting_chain
from .tiers import FieldTier

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class RoleSeedTests(TestCase):
    def test_eight_roles_seeded_with_expected_row_scope(self):
        expected_scopes = {
            "employee": "self",
            "line_manager": "own_team",
            "hr_admin": "all",
            "ee_manager": "all",
            "recruiter": "all",
            "comp_manager": "all",
            "auditor": "all",
            "sysadmin": "all",
        }
        self.assertEqual(Role.objects.count(), 8)
        for name, scope in expected_scopes.items():
            self.assertEqual(Role.objects.get(name=name).row_scope, scope)

    def test_line_manager_has_no_sensitive_tier_grant(self):
        role = Role.objects.get(name="line_manager")
        grant = role.tier_grants.get(tier=FieldTier.SENSITIVE)
        self.assertFalse(grant.can_read)
        self.assertFalse(grant.can_write)

    def test_hr_admin_can_read_and_write_sensitive_but_not_write_restricted(self):
        role = Role.objects.get(name="hr_admin")
        sensitive = role.tier_grants.get(tier=FieldTier.SENSITIVE)
        restricted = role.tier_grants.get(tier=FieldTier.RESTRICTED)
        self.assertTrue(sensitive.can_read and sensitive.can_write)
        self.assertTrue(restricted.can_read)
        self.assertFalse(restricted.can_write)


class CanAccessTierTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E100", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="e100@example.com", hire_date=date(2022, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )

    def test_public_tier_always_accessible(self):
        self.assertTrue(can_access_tier(None, FieldTier.PUBLIC, mode="read"))
        self.assertTrue(can_access_tier(self.employee, FieldTier.PUBLIC, mode="read"))

    def test_no_roles_denies_sensitive_tier(self):
        self.assertFalse(can_access_tier(self.employee, FieldTier.SENSITIVE, mode="read"))

    def test_assigned_role_grants_access(self):
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="hr_admin"))
        self.assertTrue(can_access_tier(self.employee, FieldTier.SENSITIVE, mode="read"))
        self.assertTrue(can_access_tier(self.employee, FieldTier.SENSITIVE, mode="write"))

    def test_revoked_assignment_no_longer_grants_access(self):
        assignment = RoleAssignment.objects.create(
            employee=self.employee, role=Role.objects.get(name="hr_admin")
        )
        assignment.revoked_at = assignment.granted_at
        assignment.save(update_fields=["revoked_at"])
        self.assertFalse(can_access_tier(self.employee, FieldTier.SENSITIVE, mode="read"))


class RowScopeTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.top_manager = Employee.objects.hire(
            employee_number="MGR", first_name="Top", last_name="Manager", date_of_birth=date(1970, 1, 1),
            work_email="mgr@example.com", hire_date=date(2010, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        self.direct_report = Employee.objects.hire(
            employee_number="DIRECT", first_name="Direct", last_name="Report", date_of_birth=date(1990, 1, 1),
            work_email="direct@example.com", hire_date=date(2022, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            manager=self.top_manager,
        )
        self.indirect_report = Employee.objects.hire(
            employee_number="INDIRECT", first_name="Indirect", last_name="Report", date_of_birth=date(1995, 1, 1),
            work_email="indirect@example.com", hire_date=date(2023, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            manager=self.direct_report,
        )
        self.outsider = Employee.objects.hire(
            employee_number="OUTSIDER", first_name="Outside", last_name="Team", date_of_birth=date(1990, 1, 1),
            work_email="outsider@example.com", hire_date=date(2022, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_is_in_reporting_chain_direct_and_indirect(self):
        self.assertTrue(is_in_reporting_chain(self.top_manager, self.direct_report))
        self.assertTrue(is_in_reporting_chain(self.top_manager, self.indirect_report))
        self.assertFalse(is_in_reporting_chain(self.top_manager, self.outsider))

    def test_all_scope_role_sees_everyone(self):
        RoleAssignment.objects.create(employee=self.top_manager, role=Role.objects.get(name="hr_admin"))
        self.assertTrue(has_row_access(self.top_manager, self.outsider))

    def test_own_team_scope_sees_reports_not_outsiders(self):
        RoleAssignment.objects.create(employee=self.top_manager, role=Role.objects.get(name="line_manager"))
        self.assertTrue(has_row_access(self.top_manager, self.direct_report))
        self.assertTrue(has_row_access(self.top_manager, self.indirect_report))
        self.assertFalse(has_row_access(self.top_manager, self.outsider))

    def test_self_scope_only_sees_self(self):
        RoleAssignment.objects.create(employee=self.direct_report, role=Role.objects.get(name="employee"))
        self.assertTrue(has_row_access(self.direct_report, self.direct_report))
        self.assertFalse(has_row_access(self.direct_report, self.top_manager))
        self.assertFalse(has_row_access(self.direct_report, self.outsider))

    def test_no_roles_denies_everything(self):
        self.assertFalse(has_row_access(self.outsider, self.direct_report))
        self.assertFalse(has_row_access(self.outsider, self.outsider))


class AuditLogImmutabilityTests(TestCase):
    def test_entry_cannot_be_updated(self):
        entry = AuditLogEntry.objects.create(
            actor=None, action=AuditLogEntry.Action.LOGIN, entity_type="rbac_audit.Test",
            entity_id="1", field_tier=FieldTier.PUBLIC,
        )
        entry.fields_touched = "changed"
        with self.assertRaises(ValueError):
            entry.save()

    def test_entry_cannot_be_deleted(self):
        entry = AuditLogEntry.objects.create(
            actor=None, action=AuditLogEntry.Action.LOGIN, entity_type="rbac_audit.Test",
            entity_id="1", field_tier=FieldTier.PUBLIC,
        )
        with self.assertRaises(ValueError):
            entry.delete()
        self.assertTrue(AuditLogEntry.objects.filter(pk=entry.pk).exists())


class ConsentTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E200", first_name="Consent", last_name="Test", date_of_birth=date(1990, 1, 1),
            work_email="e200@example.com", hire_date=date(2022, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )

    def test_record_and_withdraw_consent(self):
        self.assertFalse(has_active_consent(self.employee, ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID))

        consent = record_consent(
            employee=self.employee,
            purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT,
            text_version="v1",
        )
        self.assertTrue(has_active_consent(self.employee, ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID))
        self.assertTrue(
            AuditLogEntry.objects.filter(
                entity_type="rbac_audit.ConsentRecord", entity_id=str(consent.pk), action=AuditLogEntry.Action.CREATE
            ).exists()
        )

        withdraw_consent(consent)
        self.assertFalse(has_active_consent(self.employee, ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID))
        self.assertTrue(
            AuditLogEntry.objects.filter(
                entity_type="rbac_audit.ConsentRecord", entity_id=str(consent.pk), action=AuditLogEntry.Action.UPDATE
            ).exists()
        )

    def test_double_withdrawal_raises(self):
        consent = record_consent(
            employee=self.employee, purpose=ConsentRecord.Purpose.ASSESSMENT,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )
        withdraw_consent(consent)
        with self.assertRaises(ValueError):
            withdraw_consent(consent)


class EmployeeVersionApiTests(TestCase):
    """The Sprint 2 acceptance criteria, exercised end-to-end through the
    one real endpoint the RBAC/audit layer protects. This is the
    regression baseline every later module's protected API should match."""

    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        self.manager = Employee.objects.hire(
            employee_number="MGR", first_name="Manager", last_name="One", date_of_birth=date(1975, 1, 1),
            work_email="manager@example.com", hire_date=date(2010, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="manager", password="x"),
        )
        self.report = Employee.objects.hire(
            employee_number="REPORT", first_name="Direct", last_name="Report", date_of_birth=date(1992, 5, 1),
            work_email="report@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location, manager=self.manager,
            race="african", gender="female", disability_status="no",
        )
        self.outsider = Employee.objects.hire(
            employee_number="OUTSIDER", first_name="Not", last_name="OnTeam", date_of_birth=date(1988, 1, 1),
            work_email="notonteam@example.com", hire_date=date(2019, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            race="white", gender="male", disability_status="no",
            user=User.objects.create_user(username="outsider", password="x"),
        )
        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin", password="x"),
        )

        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))
        RoleAssignment.objects.create(employee=self.outsider, role=Role.objects.get(name="employee"))
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.report_version_id = self.report.current_version.id

    def _detail_url(self, version_id):
        return f"/api/v1/employee-versions/{version_id}/"

    def test_hr_admin_sees_sensitive_fields_and_access_is_logged(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(self._detail_url(self.report_version_id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["race"], "african")
        self.assertEqual(response.data["gender"], "female")

        self.assertTrue(
            AuditLogEntry.objects.filter(
                entity_type="core_hr.EmployeeVersion",
                entity_id=str(self.report_version_id),
                action=AuditLogEntry.Action.READ_SENSITIVE,
                field_tier=FieldTier.SENSITIVE,
            ).exists()
        )

    def test_line_manager_sees_own_report_but_sensitive_fields_are_stripped(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get(self._detail_url(self.report_version_id))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("race", response.data)
        self.assertNotIn("gender", response.data)
        self.assertNotIn("disability_status", response.data)
        self.assertIn("department", response.data)  # public tier still visible

    def test_line_manager_who_also_holds_base_employee_role_still_cant_see_report_sensitive_fields(self):
        # Regression: every real employee — including managers — also
        # holds the base 'employee' role (self row-scope, S:read=True, for
        # their OWN profile). A field-tier check that isn't row-scope-aware
        # per role would let that grant leak onto every record the SAME
        # person's line_manager role can reach, defeating "aggregate-only"
        # (RBAC-Roles.md) for line managers entirely. can_access_tier_for_target
        # is what prevents this — this pins the observable behavior.
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="employee"))
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get(self._detail_url(self.report_version_id))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("race", response.data)
        self.assertNotIn("gender", response.data)
        self.assertNotIn("disability_status", response.data)
        # but the manager's own record still shows sensitive fields, via
        # that same base role's self-scope grant
        own_version_id = self.manager.current_version.id
        own_response = self.client.get(self._detail_url(own_version_id))
        self.assertEqual(own_response.status_code, 200)
        self.assertIn("race", own_response.data)

    def test_line_manager_blocked_from_outsider_and_denial_is_logged(self):
        outsider_version_id = self.outsider.current_version.id
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get(self._detail_url(outsider_version_id))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                entity_type="core_hr.EmployeeVersion",
                entity_id=str(outsider_version_id),
                action=AuditLogEntry.Action.ACCESS_DENIED,
            ).exists()
        )

    def test_employee_self_scope_blocked_from_colleague(self):
        report_version_id = self.report.current_version.id
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get(self._detail_url(report_version_id))

        self.assertEqual(response.status_code, 403)

    def test_employee_self_scope_can_read_own_record_including_sensitive_fields(self):
        own_version_id = self.outsider.current_version.id
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get(self._detail_url(own_version_id))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["race"], "white")

    def test_list_only_returns_rows_within_row_scope(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/employee-versions/")

        self.assertEqual(response.status_code, 200)
        returned_ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.report_version_id, returned_ids)
        self.assertNotIn(self.outsider.current_version.id, returned_ids)
