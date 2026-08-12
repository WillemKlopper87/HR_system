from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .models import Applicant, ApplicantStageEvent, Requisition
from .services import StageTransitionError, transition_applicant


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class ApplicantStageTransitionTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department=dept, occupational_level=level, job_grade=grade,
            location=location, headcount=1, status=Requisition.Status.OPEN, opened_at=date(2026, 7, 1),
        )
        self.applicant = Applicant.objects.create(
            requisition=self.requisition, first_name="Alex", last_name="Applicant",
            email="alex@example.com", date_of_birth=date(1995, 3, 3),
        )

    def test_valid_forward_transition_succeeds_and_is_recorded(self):
        transition_applicant(self.applicant, to_stage=Applicant.Stage.SCREENED)
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.current_stage, Applicant.Stage.SCREENED)
        event = ApplicantStageEvent.objects.get(applicant=self.applicant)
        self.assertEqual(event.from_stage, Applicant.Stage.APPLIED)
        self.assertEqual(event.to_stage, Applicant.Stage.SCREENED)

    def test_skipping_stages_is_rejected(self):
        with self.assertRaises(StageTransitionError):
            transition_applicant(self.applicant, to_stage=Applicant.Stage.HIRED)
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.current_stage, Applicant.Stage.APPLIED)

    def test_rejected_is_reachable_from_any_active_stage(self):
        transition_applicant(self.applicant, to_stage=Applicant.Stage.REJECTED, rejected_reason="Not a fit")
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.current_stage, Applicant.Stage.REJECTED)
        self.assertEqual(self.applicant.rejected_reason, "Not a fit")

    def test_terminal_stages_have_no_further_transitions(self):
        transition_applicant(self.applicant, to_stage=Applicant.Stage.REJECTED)
        with self.assertRaises(StageTransitionError):
            transition_applicant(self.applicant, to_stage=Applicant.Stage.SCREENED)


class HireAutomationTests(TestCase):
    """Sprint 4 acceptance criterion: hiring an applicant creates the
    employees row with no manual re-entry."""

    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN, opened_at=date(2026, 7, 1),
        )
        self.applicant = Applicant.objects.create(
            requisition=self.requisition, first_name="Alex", last_name="Applicant",
            email="alex@example.com", date_of_birth=date(1995, 3, 3), race="african", gender="female",
            disability_status="no",
        )
        for stage in (Applicant.Stage.SCREENED, Applicant.Stage.INTERVIEW, Applicant.Stage.OFFER):
            transition_applicant(self.applicant, to_stage=stage)

    def test_hire_creates_employee_with_applicant_data_and_requisition_assignment(self):
        transition_applicant(self.applicant, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 8, 1))
        self.applicant.refresh_from_db()

        self.assertIsNotNone(self.applicant.resulting_employee)
        employee = self.applicant.resulting_employee
        self.assertEqual(employee.first_name, "Alex")
        self.assertEqual(employee.work_email, "alex@example.com")
        current = employee.current_version
        self.assertEqual(current.department, self.dept)
        self.assertEqual(current.job_grade, self.grade)
        self.assertEqual(current.race, "african")
        self.assertEqual(current.race_source, "self_identified")

    def test_hire_fills_requisition_and_stamps_closed_at(self):
        transition_applicant(self.applicant, to_stage=Applicant.Stage.HIRED)
        self.requisition.refresh_from_db()
        self.assertEqual(self.requisition.status, Requisition.Status.FILLED)
        self.assertIsNotNone(self.requisition.closed_at)

    def test_hire_with_email_already_used_by_an_employee_is_rejected(self):
        Employee.objects.hire(
            employee_number="E999", first_name="Existing", last_name="Person", date_of_birth=date(1980, 1, 1),
            work_email="alex@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        with self.assertRaises(ValueError):
            transition_applicant(self.applicant, to_stage=Applicant.Stage.HIRED)
        self.applicant.refresh_from_db()
        self.assertIsNone(self.applicant.resulting_employee)

    def test_hired_applicant_cannot_be_hired_again(self):
        transition_applicant(self.applicant, to_stage=Applicant.Stage.HIRED)
        with self.assertRaises(StageTransitionError):
            transition_applicant(self.applicant, to_stage=Applicant.Stage.HIRED)

    def test_requisition_not_filled_until_headcount_reached(self):
        self.requisition.headcount = 2
        self.requisition.save(update_fields=["headcount"])
        transition_applicant(self.applicant, to_stage=Applicant.Stage.HIRED)
        self.requisition.refresh_from_db()
        self.assertNotEqual(self.requisition.status, Requisition.Status.FILLED)
