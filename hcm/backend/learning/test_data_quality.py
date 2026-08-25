"""H3 org-wide data-quality sweep: this app's own overdue-mandatory-
training check, registered from `LearningConfig.ready()` (see
learning/data_quality.py). Mirrors performance/test_data_quality.py's
shape; reuses learning.compliance's own derivation, so these tests pin
the "wired into the registry and the org-wide sweep" half specifically —
compliance derivation itself is pinned in test_compliance.py."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from core_hr.data_quality import run_data_quality_checks
from core_hr.models import DataQualityException, Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .data_quality import overdue_training_handler
from .models import Course, CourseRequirement, TrainingRecord

TODAY = date(2026, 8, 25)


def _run_handler():
    with patch("learning.data_quality.timezone.localdate", return_value=TODAY):
        return list(overdue_training_handler())


class OverdueTrainingHandlerTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Operations", code="OPS")
        self.level = OccupationalLevel.objects.get(code="TOP")
        self.grade = JobGrade.objects.create(name="G1", code="G1", occupational_level=self.level)
        self.location = Location.objects.create(name="HO", code="HO", province=Location.Province.GAUTENG)
        self.employee = Employee.objects.hire(
            employee_number="E0060", first_name="Overdue", last_name="Training", date_of_birth=date(1990, 1, 1),
            work_email="overdue.training@example.com", hire_date=TODAY - timedelta(days=365),
            department=self.dept, occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        self.course = Course.objects.create(name="Safety Induction", mandatory=True)

    def test_overdue_employee_is_flagged(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=30,
        )
        flagged = _run_handler()
        self.assertEqual([e for e, _ in flagged], [self.employee])

    def test_not_yet_due_employee_is_not_flagged(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=5),
            due_within_days=90,
        )
        self.assertEqual(_run_handler(), [])

    def test_wired_into_the_org_wide_sweep(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=30,
        )
        with patch("learning.data_quality.timezone.localdate", return_value=TODAY):
            run_data_quality_checks()

        self.assertTrue(
            DataQualityException.objects.filter(
                employee=self.employee,
                exception_type=DataQualityException.ExceptionType.MANDATORY_TRAINING_OVERDUE,
                resolved_at__isnull=True,
            ).exists()
        )

    def test_completing_the_course_auto_resolves_the_exception(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=30,
        )
        with patch("learning.data_quality.timezone.localdate", return_value=TODAY):
            run_data_quality_checks()
        self.assertTrue(
            DataQualityException.objects.filter(
                employee=self.employee, exception_type=DataQualityException.ExceptionType.MANDATORY_TRAINING_OVERDUE,
                resolved_at__isnull=True,
            ).exists()
        )

        TrainingRecord.objects.create(
            employee=self.employee, course=self.course, title="Safety Induction",
            status=TrainingRecord.Status.COMPLETED, completion_date=TODAY,
        )
        with patch("learning.data_quality.timezone.localdate", return_value=TODAY):
            run_data_quality_checks()
        self.assertFalse(
            DataQualityException.objects.filter(
                employee=self.employee, exception_type=DataQualityException.ExceptionType.MANDATORY_TRAINING_OVERDUE,
                resolved_at__isnull=True,
            ).exists()
        )
