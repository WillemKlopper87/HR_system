"""Service-layer tests for C6 compliance derivation (learning/compliance.py).
Mirrors learning/tests.py's shape (direct model/service tests, not API
tests -- those live in test_api.py). Every branch of design spec §6's
status derivation gets its own test."""
from __future__ import annotations

from datetime import date, timedelta

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .compliance import compliance_for_employee
from .models import Course, CourseRequirement, TrainingRecord

TODAY = date(2026, 8, 25)


def _seed_reference_data(dept_code="ENG", level_code="SKILLED"):
    dept, _ = Department.objects.get_or_create(code=dept_code, defaults={"name": dept_code.title()})
    level = OccupationalLevel.objects.get(code=level_code)
    grade, _ = JobGrade.objects.get_or_create(
        code=f"G-{dept_code}-{level_code}", defaults={"name": "Grade", "occupational_level": level}
    )
    location, _ = Location.objects.get_or_create(
        code="HO", defaults={"name": "Head Office", "province": Location.Province.GAUTENG}
    )
    return dept, level, grade, location


def _hire(number, *, department, occupational_level, job_grade, location, hire_date=date(2020, 1, 1)):
    return Employee.objects.hire(
        employee_number=number, first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
        work_email=f"{number.lower()}@example.com", hire_date=hire_date, department=department,
        occupational_level=occupational_level, job_grade=job_grade, location=location,
    )


class ComplianceDerivationTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.other_dept, self.other_level, self.other_grade, _ = _seed_reference_data(
            dept_code="FIN", level_code="SENIOR"
        )
        self.course = Course.objects.create(name="POPIA Awareness", mandatory=True)

    def _employee(self, number="E100", **kwargs):
        kwargs.setdefault("department", self.dept)
        kwargs.setdefault("occupational_level", self.level)
        kwargs.setdefault("job_grade", self.grade)
        kwargs.setdefault("location", self.location)
        return _hire(number, **kwargs)

    def test_not_yet_applicable_requirement_produces_no_status(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY + timedelta(days=30),
            due_within_days=90,
        )
        employee = self._employee()
        self.assertEqual(compliance_for_employee(employee, as_of=TODAY), [])

    def test_due_not_yet_overdue(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=10),
            due_within_days=90,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=365))
        [status] = compliance_for_employee(employee, as_of=TODAY)
        self.assertEqual(status.status, "due")

    def test_overdue_when_no_completion_past_due_date(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=90,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=365))
        [status] = compliance_for_employee(employee, as_of=TODAY)
        self.assertEqual(status.status, "overdue")
        self.assertEqual(status.due_date, TODAY - timedelta(days=110))

    def test_compliant_with_no_expiry(self):
        self.course.validity_days = None
        self.course.save()
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=365),
            due_within_days=30,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=1000))
        TrainingRecord.objects.create(
            employee=employee, course=self.course, title="POPIA Awareness",
            status=TrainingRecord.Status.COMPLETED, completion_date=TODAY - timedelta(days=900),
        )
        [status] = compliance_for_employee(employee, as_of=TODAY)
        self.assertEqual(status.status, "compliant")

    def test_compliant_then_expired_renewal(self):
        self.course.validity_days = 365
        self.course.save()
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=1000),
            due_within_days=30,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=1000))
        TrainingRecord.objects.create(
            employee=employee, course=self.course, title="POPIA Awareness",
            status=TrainingRecord.Status.COMPLETED, completion_date=TODAY - timedelta(days=400),
        )
        [status] = compliance_for_employee(employee, as_of=TODAY)
        self.assertEqual(status.status, "overdue")
        self.assertEqual(status.due_date, TODAY - timedelta(days=35))

    def test_compliant_within_renewal_window(self):
        self.course.validity_days = 365
        self.course.save()
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=1000),
            due_within_days=30,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=1000))
        TrainingRecord.objects.create(
            employee=employee, course=self.course, title="POPIA Awareness",
            status=TrainingRecord.Status.COMPLETED, completion_date=TODAY - timedelta(days=100),
        )
        [status] = compliance_for_employee(employee, as_of=TODAY)
        self.assertEqual(status.status, "compliant")

    def test_department_only_scope_excludes_other_department(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=90,
        )
        outsider = self._employee(
            number="E200", department=self.other_dept, occupational_level=self.other_level,
            job_grade=self.other_grade, hire_date=TODAY - timedelta(days=365),
        )
        self.assertEqual(compliance_for_employee(outsider, as_of=TODAY), [])

    def test_occupational_level_only_scope(self):
        CourseRequirement.objects.create(
            course=self.course, occupational_level=self.other_level, effective_from=TODAY - timedelta(days=200),
            due_within_days=90,
        )
        senior_in_other_dept = self._employee(
            number="E300", department=self.other_dept, occupational_level=self.other_level,
            job_grade=self.other_grade, hire_date=TODAY - timedelta(days=365),
        )
        [status] = compliance_for_employee(senior_in_other_dept, as_of=TODAY)
        self.assertEqual(status.status, "overdue")

        not_senior = self._employee(number="E301", hire_date=TODAY - timedelta(days=365))
        self.assertEqual(compliance_for_employee(not_senior, as_of=TODAY), [])

    def test_both_null_scope_applies_org_wide(self):
        CourseRequirement.objects.create(
            course=self.course, effective_from=TODAY - timedelta(days=200), due_within_days=90,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=365))
        other_dept_employee = self._employee(
            number="E400", department=self.other_dept, occupational_level=self.other_level,
            job_grade=self.other_grade, hire_date=TODAY - timedelta(days=365),
        )
        self.assertEqual(len(compliance_for_employee(employee, as_of=TODAY)), 1)
        self.assertEqual(len(compliance_for_employee(other_dept_employee, as_of=TODAY)), 1)

    def test_department_and_level_intersection(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, occupational_level=self.level,
            effective_from=TODAY - timedelta(days=200), due_within_days=90,
        )
        matching = self._employee(hire_date=TODAY - timedelta(days=365))
        [status] = compliance_for_employee(matching, as_of=TODAY)
        self.assertEqual(status.status, "overdue")

        # Right department, wrong level.
        wrong_level = self._employee(
            number="E500", department=self.dept, occupational_level=self.other_level,
            job_grade=self.other_grade, hire_date=TODAY - timedelta(days=365),
        )
        self.assertEqual(compliance_for_employee(wrong_level, as_of=TODAY), [])

    def test_subject_since_uses_later_of_rule_and_version_start(self):
        # Rule predates the employee's hire -- clock starts at hire (the
        # version's own valid_from), not the rule's effective_from.
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=date(2015, 1, 1), due_within_days=90,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=10))
        [status] = compliance_for_employee(employee, as_of=TODAY)
        self.assertEqual(status.status, "due")
        self.assertEqual(status.due_date, TODAY - timedelta(days=10) + timedelta(days=90))

    def test_inactive_requirement_is_ignored(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=90, active=False,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=365))
        self.assertEqual(compliance_for_employee(employee, as_of=TODAY), [])

    def test_inactive_course_is_ignored(self):
        self.course.active = False
        self.course.save()
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=90,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=365))
        self.assertEqual(compliance_for_employee(employee, as_of=TODAY), [])

    def test_uncompleted_incomplete_status_does_not_satisfy_requirement(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=90,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=365))
        TrainingRecord.objects.create(
            employee=employee, course=self.course, title="POPIA Awareness",
            status=TrainingRecord.Status.IN_PROGRESS,
        )
        [status] = compliance_for_employee(employee, as_of=TODAY)
        self.assertEqual(status.status, "overdue")

    def test_free_text_record_without_course_link_does_not_satisfy_requirement(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=200),
            due_within_days=90,
        )
        employee = self._employee(hire_date=TODAY - timedelta(days=365))
        TrainingRecord.objects.create(
            employee=employee, title="POPIA Awareness", status=TrainingRecord.Status.COMPLETED,
            completion_date=TODAY - timedelta(days=5),
        )
        [status] = compliance_for_employee(employee, as_of=TODAY)
        self.assertEqual(status.status, "overdue")
