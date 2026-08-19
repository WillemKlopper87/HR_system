"""H3: OpenAPI schema + Swagger UI are hr_admin-only -- operational/developer
tooling that exposes every field name and endpoint shape in one place, not
an employee-facing feature."""
from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

User = get_user_model()


class SchemaAccessTests(TestCase):
    def setUp(self):
        cache.clear()
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

    def _login(self, employee):
        client = APIClient()
        client.force_authenticate(user=employee.user)
        return client

    def test_hr_admin_can_fetch_the_schema_and_docs(self):
        client = self._login(self.hr_admin)
        schema = client.get("/api/schema/")
        self.assertEqual(schema.status_code, 200)
        docs = client.get("/api/docs/")
        self.assertEqual(docs.status_code, 200)

    def test_auditor_is_forbidden(self):
        client = self._login(self.auditor)
        self.assertEqual(client.get("/api/schema/").status_code, 403)
        self.assertEqual(client.get("/api/docs/").status_code, 403)

    def test_plain_employee_is_forbidden(self):
        client = self._login(self.employee)
        self.assertEqual(client.get("/api/schema/").status_code, 403)
        self.assertEqual(client.get("/api/docs/").status_code, 403)

    def test_anonymous_is_forbidden(self):
        client = APIClient()
        self.assertEqual(client.get("/api/schema/").status_code, 403)
