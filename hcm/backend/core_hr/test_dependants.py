from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Department, Dependant, Employee, EmergencyContact, JobGrade, Location, OccupationalLevel

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class DependantEmergencyContactApiTests(TestCase):
    """C2 design spec §2.8, §5.2: self-or-hr_admin only — narrower than the
    generic row-scope shape used by e.g. learning.Certification, since a
    line_manager has no legitimate reason to manage a report's dependants
    or emergency contacts."""

    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin-dep@example.com", hire_date=date(2015, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hradmin-dep", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.staff = Employee.objects.hire(
            employee_number="E100", first_name="Staff", last_name="Member", date_of_birth=date(1992, 1, 1),
            work_email="staff-dep@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="staff-dep", password="x"),
        )
        RoleAssignment.objects.create(employee=self.staff, role=Role.objects.get(name="employee"))

        self.manager = Employee.objects.hire(
            employee_number="M100", first_name="Manager", last_name="Person", date_of_birth=date(1980, 1, 1),
            work_email="manager-dep@example.com", hire_date=date(2018, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="manager-dep", password="x"),
        )
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))
        version = self.staff.current_version
        version.manager = self.manager
        version.save(update_fields=["manager"])

    def test_employee_can_create_own_dependant(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.post(
            "/api/v1/dependants/",
            {"employee": self.staff.id, "first_name": "Jane", "last_name": "Member", "relationship": "spouse"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Dependant.objects.filter(employee=self.staff).count(), 1)

    def test_line_manager_cannot_create_dependant_for_report(self):
        """Deliberately narrower than has_row_access — see the model/
        serializer docstrings (C2 design spec §2.8)."""
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/dependants/",
            {"employee": self.staff.id, "first_name": "Jane", "last_name": "Member", "relationship": "spouse"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Dependant.objects.filter(employee=self.staff).count(), 0)

    def test_hr_admin_can_create_dependant_on_behalf_of_employee(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/dependants/",
            {"employee": self.staff.id, "first_name": "Jane", "last_name": "Member", "relationship": "child"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_outsider_does_not_see_dependant_in_list(self):
        Dependant.objects.create(employee=self.staff, first_name="Jane", last_name="Member", relationship="spouse")
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dependants/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_outsider_gets_403_on_detail(self):
        dependant = Dependant.objects.create(
            employee=self.staff, first_name="Jane", last_name="Member", relationship="spouse"
        )
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get(f"/api/v1/dependants/{dependant.id}/")
        self.assertEqual(response.status_code, 403)

    def test_employee_can_delete_own_dependant(self):
        dependant = Dependant.objects.create(
            employee=self.staff, first_name="Jane", last_name="Member", relationship="spouse"
        )
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.delete(f"/api/v1/dependants/{dependant.id}/")
        self.assertEqual(response.status_code, 204)

    def test_only_one_primary_emergency_contact_per_employee(self):
        EmergencyContact.objects.create(employee=self.staff, name="Jane", phone="0821234567", is_primary=True)
        with self.assertRaises(Exception):
            EmergencyContact.objects.create(employee=self.staff, name="Sam", phone="0839876543", is_primary=True)

    def test_employee_can_create_own_emergency_contact(self):
        self.client.force_authenticate(user=self.staff.user)
        response = self.client.post(
            "/api/v1/emergency-contacts/",
            {"employee": self.staff.id, "name": "Jane", "phone": "0821234567", "is_primary": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_line_manager_cannot_read_reports_emergency_contact(self):
        """Deliberate, recorded gap (design spec §9) — not extended to
        line_manager even for own-team, unlike EmployeeDocument reads."""
        contact = EmergencyContact.objects.create(employee=self.staff, name="Jane", phone="0821234567")
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get(f"/api/v1/emergency-contacts/{contact.id}/")
        self.assertEqual(response.status_code, 403)
