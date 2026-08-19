from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .models import Position


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


def _hr_admin(dept, level, grade, location):
    from django.contrib.auth import get_user_model
    from rbac_audit.models import Role, RoleAssignment

    User = get_user_model()
    emp = Employee.objects.hire(
        employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
        work_email="hradmin@example.com", hire_date=date(2020, 1, 1), department=dept,
        occupational_level=level, job_grade=grade, location=location,
        user=User.objects.create_user(username="hradmin_est", password="x"),
    )
    RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name="hr_admin"))
    return emp


class PositionModelTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def test_position_defaults_to_draft_with_no_current_step(self):
        position = Position.objects.create(
            post_number="P-00001", title="Software Engineer", department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        self.assertEqual(position.status, Position.Status.DRAFT)
        self.assertEqual(position.current_step, 0)

    def test_post_number_is_unique(self):
        Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location,
        )
        with self.assertRaises(Exception):
            Position.objects.create(
                post_number="P-00001", title="B", department=self.dept, occupational_level=self.level,
                job_grade=self.grade, location=self.location,
            )

    def test_is_vacant_false_when_draft_even_with_no_occupant(self):
        """A draft/in_review position isn't on the establishment yet -- it
        doesn't count as a real vacancy until approved."""
        position = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )
        self.assertFalse(position.is_vacant)

    def test_is_vacant_true_when_approved_with_no_occupant(self):
        position = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        self.assertTrue(position.is_vacant)
        self.assertIsNone(position.current_occupant)

    def test_is_vacant_false_once_occupied(self):
        position = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        Employee.objects.hire(
            employee_number="E001", first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="alex@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=position,
        )
        self.assertFalse(position.is_vacant)
        self.assertIsNotNone(position.current_occupant)

    def test_vacant_queryset_excludes_occupied_and_unapproved(self):
        occupied = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        Employee.objects.hire(
            employee_number="E001", first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="alex@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=occupied,
        )
        draft = Position.objects.create(
            post_number="P-00002", title="B", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )
        vacant = Position.objects.create(
            post_number="P-00003", title="C", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        self.assertEqual(list(Position.objects.vacant()), [vacant])
        self.assertNotIn(occupied, Position.objects.vacant())
        self.assertNotIn(draft, Position.objects.vacant())
