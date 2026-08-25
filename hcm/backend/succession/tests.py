from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.db import IntegrityError
from django.test import TestCase
from establishment.models import Position

from .models import CriticalPost, SuccessionCandidate


def _seed_reference_data():
    dept = Department.objects.create(name="Finance", code="FIN")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class SuccessionModelTestCase(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.position = Position.objects.create(
            post_number="P-00001", title="Head of Finance", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )

    def _hire(self, number):
        return Employee.objects.hire(
            employee_number=number, first_name="Case", last_name=number, date_of_birth=date(1990, 1, 1),
            work_email=f"{number.lower()}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def _occupy(self, position, employee):
        """`employee.current_version` is a fresh query per access (not
        cached on the Employee instance) -- mutating and saving it in one
        expression discards the change, so this fetches it into a local
        first."""
        version = employee.current_version
        version.position = position
        version.save(update_fields=["position"])
        return version


class CriticalPostModelTests(SuccessionModelTestCase):
    def test_defaults_to_active(self):
        flag = CriticalPost.objects.create(position=self.position, reason="Sole SME on treasury.")
        self.assertTrue(flag.active)

    def test_only_one_row_per_position(self):
        CriticalPost.objects.create(position=self.position, reason="First")
        with self.assertRaises(IntegrityError):
            CriticalPost.objects.create(position=self.position, reason="Second")

    def test_unflag_preserves_the_row(self):
        flag = CriticalPost.objects.create(position=self.position, reason="Sole SME on treasury.")
        flag.active = False
        flag.save(update_fields=["active"])
        flag.refresh_from_db()
        self.assertFalse(flag.active)
        self.assertEqual(CriticalPost.objects.count(), 1)

    def test_str_reflects_active_state(self):
        flag = CriticalPost.objects.create(position=self.position, reason="x")
        self.assertIn("critical", str(flag))
        flag.active = False
        self.assertIn("unflagged", str(flag))


class SuccessionCandidateModelTests(SuccessionModelTestCase):
    def setUp(self):
        super().setUp()
        self.critical_post = CriticalPost.objects.create(position=self.position, reason="x")
        self.candidate_employee = self._hire("E0100")

    def test_defaults_to_active(self):
        candidate = SuccessionCandidate.objects.create(
            critical_post=self.critical_post, employee=self.candidate_employee,
            readiness=SuccessionCandidate.Readiness.READY_NOW,
        )
        self.assertTrue(candidate.active)

    def test_two_active_nominations_for_the_same_pair_is_rejected_at_db_level(self):
        SuccessionCandidate.objects.create(
            critical_post=self.critical_post, employee=self.candidate_employee,
            readiness=SuccessionCandidate.Readiness.READY_NOW,
        )
        with self.assertRaises(IntegrityError):
            SuccessionCandidate.objects.create(
                critical_post=self.critical_post, employee=self.candidate_employee,
                readiness=SuccessionCandidate.Readiness.DEVELOPMENT_NEEDED,
            )

    def test_a_withdrawn_then_renominated_pair_keeps_both_rows(self):
        first = SuccessionCandidate.objects.create(
            critical_post=self.critical_post, employee=self.candidate_employee,
            readiness=SuccessionCandidate.Readiness.DEVELOPMENT_NEEDED,
        )
        first.active = False
        first.save(update_fields=["active"])
        second = SuccessionCandidate.objects.create(
            critical_post=self.critical_post, employee=self.candidate_employee,
            readiness=SuccessionCandidate.Readiness.READY_NOW,
        )
        self.assertEqual(
            SuccessionCandidate.objects.filter(critical_post=self.critical_post, employee=self.candidate_employee).count(),
            2,
        )
        self.assertTrue(second.active)

    def test_ready_soon_set_contains_ready_now_and_1_2_years_only(self):
        self.assertEqual(
            set(SuccessionCandidate.READY_SOON),
            {SuccessionCandidate.Readiness.READY_NOW, SuccessionCandidate.Readiness.READY_1_2_YEARS},
        )
