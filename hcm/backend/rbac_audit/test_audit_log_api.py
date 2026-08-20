"""H3: the audit-log viewer — filterable list + CSV export for hr_admin and
auditor, and the "every auditor read is itself audited" rule from the
role's own seed description."""
from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .audit import log_access
from .models import AuditLogEntry, Role, RoleAssignment
from .tiers import FieldTier

User = get_user_model()


class AuditLogApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        dept = Department.objects.create(name="Engineering", code="ENG")
        level = OccupationalLevel.objects.get(code="TOP")
        grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
        location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)

        def hire(number, username, role_name):
            employee = Employee.objects.hire(
                employee_number=number, first_name=username, last_name="Test", date_of_birth=date(1990, 1, 1),
                work_email=f"{username}@example.com", hire_date=date(2021, 1, 1), department=dept,
                occupational_level=level, job_grade=grade, location=location,
                user=User.objects.create_user(username=username, password="correct-password"),
            )
            RoleAssignment.objects.create(employee=employee, role=Role.objects.get(name=role_name))
            return employee

        self.hr_admin = hire("E001", "hradmintest", "hr_admin")
        self.auditor = hire("E002", "auditortest", "auditor")
        self.employee = hire("E003", "employeetest", "employee")

        log_access(
            actor=self.employee, action=AuditLogEntry.Action.READ_SENSITIVE,
            entity_type="core_hr.EmployeeVersion", entity_id=self.employee.pk, field_tier=FieldTier.SENSITIVE,
            fields_touched="race,gender",
        )
        log_access(
            actor=self.hr_admin, action=AuditLogEntry.Action.UPDATE,
            entity_type="compensation.PayBand", entity_id=1, field_tier=FieldTier.RESTRICTED,
        )

    def _login(self, employee):
        client = APIClient()
        client.force_authenticate(user=employee.user)
        return client

    def test_hr_admin_and_auditor_can_list(self):
        for actor in (self.hr_admin, self.auditor):
            client = self._login(actor)
            response = client.get("/api/v1/auth/audit-log/")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertGreaterEqual(len(response.data["results"]), 2)

    def test_plain_employee_is_forbidden(self):
        client = self._login(self.employee)
        response = client.get("/api/v1/auth/audit-log/")
        self.assertEqual(response.status_code, 403)

    def test_viewing_the_log_is_itself_audited(self):
        before = AuditLogEntry.objects.count()
        client = self._login(self.auditor)
        client.get("/api/v1/auth/audit-log/")
        self.assertEqual(AuditLogEntry.objects.count(), before + 1)
        newest = AuditLogEntry.objects.order_by("-timestamp", "-id").first()
        self.assertEqual(newest.actor, self.auditor)
        self.assertEqual(newest.entity_type, "rbac_audit.AuditLogEntry")

    def test_filter_by_actor(self):
        client = self._login(self.hr_admin)
        response = client.get(f"/api/v1/auth/audit-log/?actor={self.employee.id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(r["actor"] == self.employee.id for r in response.data["results"]))

    def test_filter_by_action_and_field_tier(self):
        client = self._login(self.hr_admin)
        response = client.get("/api/v1/auth/audit-log/?action=update&field_tier=R")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(r["action"] == "update" and r["field_tier"] == "R" for r in response.data["results"]))

    def test_filter_by_entity_type_substring(self):
        client = self._login(self.hr_admin)
        response = client.get("/api/v1/auth/audit-log/?entity_type=PayBand")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all("PayBand" in r["entity_type"] for r in response.data["results"]))

    def test_date_range_filter_excludes_out_of_range_entries(self):
        client = self._login(self.hr_admin)
        response = client.get("/api/v1/auth/audit-log/?date_from=2099-01-01")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_csv_export(self):
        client = self._login(self.auditor)
        response = client.get("/api/v1/auth/audit-log/export/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        body = response.content.decode("utf-8")
        self.assertIn("timestamp,actor_employee_number", body)
        self.assertIn("compensation.PayBand", body)

    def test_export_is_forbidden_for_a_plain_employee(self):
        client = self._login(self.employee)
        response = client.get("/api/v1/auth/audit-log/export/")
        self.assertEqual(response.status_code, 403)
