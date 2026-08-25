from __future__ import annotations

from datetime import date, timedelta

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase
from django.utils import timezone

from .models import Certification, EmployeeSkill, Skill
from .queries import skill_names_for_employee


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class CertificationExpiryTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E100", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="e100@example.com", hire_date=date(2021, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location,
        )

    def test_no_expiry_date_is_never_expired(self):
        cert = Certification.objects.create(employee=self.employee, name="No expiry")
        self.assertFalse(cert.is_expired)

    def test_future_expiry_date_is_not_expired(self):
        cert = Certification.objects.create(
            employee=self.employee, name="Future", expiry_date=timezone.localdate() + timedelta(days=30)
        )
        self.assertFalse(cert.is_expired)

    def test_past_expiry_date_is_expired(self):
        cert = Certification.objects.create(
            employee=self.employee, name="Past", expiry_date=timezone.localdate() - timedelta(days=1)
        )
        self.assertTrue(cert.is_expired)


class SkillNamesForEmployeeQueryTests(TestCase):
    """learning/queries.py -- the read-only seam succession's candidate
    cards use for skill context (C6, docs/superpowers/specs/2026-08-25-
    succession-talent-pools-design.md §2.7)."""

    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E101", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="e101@example.com", hire_date=date(2021, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location,
        )

    def test_no_skills_returns_empty_list(self):
        self.assertEqual(skill_names_for_employee(self.employee.id), [])

    def test_returns_skill_names_ordered_alphabetically(self):
        zebra = Skill.objects.create(name="Zebra Wrangling")
        alpha = Skill.objects.create(name="Accounting")
        EmployeeSkill.objects.create(employee=self.employee, skill=zebra)
        EmployeeSkill.objects.create(employee=self.employee, skill=alpha)
        self.assertEqual(skill_names_for_employee(self.employee.id), ["Accounting", "Zebra Wrangling"])
