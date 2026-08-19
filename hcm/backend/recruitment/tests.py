from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase
from establishment.models import Position

from .models import Applicant, ApplicantStageEvent, Requisition
from .services import (
    StageTransitionError,
    backfill_requisition_positions,
    transition_applicant,
    validate_requisition_positions,
)


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


def _approved_position(post_number, dept, level, grade, location):
    return Position.objects.create(
        post_number=post_number, title="Call Centre Agent", department=dept, occupational_level=level,
        job_grade=grade, location=location, status=Position.Status.APPROVED,
    )


class ValidateRequisitionPositionsTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def test_matching_count_of_approved_vacant_positions_is_valid(self):
        positions = [
            _approved_position(f"P-{i:05d}", self.dept, self.level, self.grade, self.location) for i in range(3)
        ]
        validate_requisition_positions(positions, headcount=3)  # must not raise

    def test_count_mismatch_raises(self):
        positions = [_approved_position("P-00001", self.dept, self.level, self.grade, self.location)]
        with self.assertRaises(ValueError):
            validate_requisition_positions(positions, headcount=2)

    def test_unapproved_position_raises(self):
        position = Position.objects.create(
            post_number="P-00001", title="X", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.DRAFT,
        )
        with self.assertRaises(ValueError):
            validate_requisition_positions([position], headcount=1)

    def test_already_occupied_position_raises(self):
        position = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        Employee.objects.hire(
            employee_number="E001", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="a.b@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=position,
        )
        with self.assertRaises(ValueError):
            validate_requisition_positions([position], headcount=1)

    def test_position_already_claimed_by_another_open_requisition_raises(self):
        position = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        other = Requisition.objects.create(
            title="Other req", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN,
        )
        other.positions.add(position)
        with self.assertRaises(ValueError):
            validate_requisition_positions([position], headcount=1)

    def test_position_claimed_by_a_closed_requisition_is_available_again(self):
        position = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        other = Requisition.objects.create(
            title="Other req", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.CLOSED,
        )
        other.positions.add(position)
        validate_requisition_positions([position], headcount=1)  # must not raise

    def test_already_linked_position_is_allowed_even_once_filled(self):
        """A position this SAME requisition already claimed stays valid
        even after it's since been filled by one of the requisition's own
        hires -- an unrelated later PATCH must not be rejected just
        because is_vacant flipped to False for an already-committed post."""
        position = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        requisition = Requisition.objects.create(
            title="Req", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN,
        )
        requisition.positions.add(position)
        Employee.objects.hire(
            employee_number="E001", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="a.b@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=position,
        )
        validate_requisition_positions([position], headcount=1, requisition=requisition)  # must not raise


class HireAssignsPositionTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.p1 = _approved_position("P-00001", self.dept, self.level, self.grade, self.location)
        self.p2 = _approved_position("P-00002", self.dept, self.level, self.grade, self.location)
        self.requisition = Requisition.objects.create(
            title="Agent", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=2, status=Requisition.Status.OPEN,
        )
        self.requisition.positions.set([self.p1, self.p2])

    def _applicant(self, number):
        return Applicant.objects.create(
            requisition=self.requisition, first_name="App", last_name=number, email=f"{number}@example.com",
            date_of_birth=date(1995, 1, 1), current_stage=Applicant.Stage.OFFER,
        )

    def test_first_hire_takes_the_lowest_post_number(self):
        applicant = self._applicant("A")
        transition_applicant(applicant, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 1))
        applicant.refresh_from_db()
        self.assertEqual(applicant.resulting_employee.current_version.position_id, self.p1.id)

    def test_second_sequential_hire_takes_the_next_still_vacant_position(self):
        first = self._applicant("A")
        transition_applicant(first, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 1))

        second = self._applicant("B")
        transition_applicant(second, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 2))
        second.refresh_from_db()
        self.assertEqual(second.resulting_employee.current_version.position_id, self.p2.id)

    def test_requisition_auto_fills_once_every_linked_position_is_occupied(self):
        first = self._applicant("A")
        transition_applicant(first, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 1))
        second = self._applicant("B")
        transition_applicant(second, to_stage=Applicant.Stage.HIRED, hire_date=date(2026, 1, 2))

        self.requisition.refresh_from_db()
        self.assertEqual(self.requisition.status, Requisition.Status.FILLED)


class BackfillRequisitionPositionsTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def test_closed_requisition_with_a_resulting_hire_gets_linked(self):
        requisition = Requisition.objects.create(
            title="Legacy", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.FILLED,
        )
        employee = Employee.objects.hire(
            employee_number="E0070", first_name="Legacy", last_name="Hire", date_of_birth=date(1990, 1, 1),
            work_email="legacy.hire@example.com", hire_date=date(2023, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        applicant = Applicant.objects.create(
            requisition=requisition, first_name="Legacy", last_name="Hire", email="legacy.hire@example.com",
            date_of_birth=date(1990, 1, 1), current_stage=Applicant.Stage.HIRED, resulting_employee=employee,
        )
        # this employee predates C1 -- backfill their position first, same
        # as establishment.services.backfill_positions_for_current_employees
        from establishment.services import backfill_positions_for_current_employees

        backfill_positions_for_current_employees()
        employee.refresh_from_db()
        backfilled_position_id = employee.current_version.position_id
        self.assertIsNotNone(backfilled_position_id)

        linked = backfill_requisition_positions()

        self.assertEqual(linked, 1)
        requisition.refresh_from_db()
        self.assertEqual(list(requisition.positions.values_list("id", flat=True)), [backfilled_position_id])

    def test_closed_requisition_with_multiple_hires_links_every_distinct_position(self):
        """headcount > 1 historical requisitions can have several distinct
        HIRED applicants -- each backfilled Position (1:1 per employee,
        never shared) belongs on the requisition, not just the first one
        found."""
        requisition = Requisition.objects.create(
            title="Legacy multi", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=2, status=Requisition.Status.CLOSED,
        )
        employee_a = Employee.objects.hire(
            employee_number="E0071", first_name="Legacy", last_name="HireA", date_of_birth=date(1990, 1, 1),
            work_email="legacy.hirea@example.com", hire_date=date(2023, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        employee_b = Employee.objects.hire(
            employee_number="E0072", first_name="Legacy", last_name="HireB", date_of_birth=date(1990, 1, 2),
            work_email="legacy.hireb@example.com", hire_date=date(2023, 1, 2), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        Applicant.objects.create(
            requisition=requisition, first_name="Legacy", last_name="HireA", email="legacy.hirea@example.com",
            date_of_birth=date(1990, 1, 1), current_stage=Applicant.Stage.HIRED, resulting_employee=employee_a,
        )
        Applicant.objects.create(
            requisition=requisition, first_name="Legacy", last_name="HireB", email="legacy.hireb@example.com",
            date_of_birth=date(1990, 1, 2), current_stage=Applicant.Stage.HIRED, resulting_employee=employee_b,
        )
        from establishment.services import backfill_positions_for_current_employees

        backfill_positions_for_current_employees()
        employee_a.refresh_from_db()
        employee_b.refresh_from_db()
        position_id_a = employee_a.current_version.position_id
        position_id_b = employee_b.current_version.position_id
        self.assertIsNotNone(position_id_a)
        self.assertIsNotNone(position_id_b)
        self.assertNotEqual(position_id_a, position_id_b)

        linked = backfill_requisition_positions()

        self.assertEqual(linked, 1)  # one requisition backfilled (not two position-links)
        requisition.refresh_from_db()
        self.assertEqual(
            set(requisition.positions.values_list("id", flat=True)), {position_id_a, position_id_b}
        )

    def test_open_requisition_with_no_resulting_hire_is_left_unlinked(self):
        Requisition.objects.create(
            title="Still open", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN,
        )
        linked = backfill_requisition_positions()
        self.assertEqual(linked, 0)
