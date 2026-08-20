from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase, override_settings

from .models import Position, PositionApprovalStep
from .services import (
    ApprovalError,
    backfill_positions_for_current_employees,
    decide_step,
    propose_position,
    revise_and_resubmit,
    submit_for_approval,
)


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

    def test_current_occupant_is_queried_once_per_instance(self):
        """The Positions page's serializer reads current_occupant twice per
        row -- once for is_vacant, once for current_incumbent_number -- on
        the one page whose entire job is listing every post (151+ at the
        design spec's own stated scale). Caching it per instance halves
        that; every request builds fresh instances from a fresh queryset,
        so nothing carries over between them."""
        position = Position.objects.create(
            post_number="P-00001", title="A", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        Employee.objects.hire(
            employee_number="E001", first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="alex@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, position=position,
        )
        fresh = Position.objects.get(pk=position.pk)
        with self.assertNumQueries(1):
            self.assertFalse(fresh.is_vacant)
            self.assertEqual(fresh.current_occupant.employee.employee_number, "E001")

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


class ApprovalChainTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def _propose(self):
        return propose_position(
            title="Software Engineer", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location,
        )

    def test_propose_creates_a_draft_with_a_post_number(self):
        position = self._propose()
        self.assertEqual(position.status, Position.Status.DRAFT)
        self.assertTrue(position.post_number)

    def test_post_numbers_increment_sequentially(self):
        first = self._propose()
        second = self._propose()
        self.assertNotEqual(first.post_number, second.post_number)
        first_n = int("".join(ch for ch in first.post_number if ch.isdigit()))
        second_n = int("".join(ch for ch in second.post_number if ch.isdigit()))
        self.assertEqual(second_n, first_n + 1)

    def test_submit_moves_draft_to_in_review_at_step_zero(self):
        position = self._propose()
        submit_for_approval(position)
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.IN_REVIEW)
        self.assertEqual(position.current_step, 0)

    def test_submit_twice_raises(self):
        position = self._propose()
        submit_for_approval(position)
        with self.assertRaises(ApprovalError):
            submit_for_approval(position)

    @override_settings(POSITION_APPROVAL_CHAIN=["comp_manager", "accounting_officer"])
    def test_full_two_step_chain_approves(self):
        position = self._propose()
        submit_for_approval(position)

        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED, comment="looks fine")
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.IN_REVIEW)
        self.assertEqual(position.current_step, 1)

        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.APPROVED)

        steps = list(position.approval_steps.order_by("step_index"))
        self.assertEqual([s.role for s in steps], ["comp_manager", "accounting_officer"])
        self.assertEqual([s.decision for s in steps], ["approved", "approved"])
        self.assertEqual(steps[0].comment, "looks fine")

    @override_settings(POSITION_APPROVAL_CHAIN=["accounting_officer"])
    def test_a_different_shorter_chain_is_honoured_with_no_code_changes(self):
        """This is the test that actually proves 'configurable' holds --
        not just that the default 2-step shape works."""
        position = self._propose()
        submit_for_approval(position)
        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.APPROVED)
        self.assertEqual(position.approval_steps.count(), 1)
        self.assertEqual(position.approval_steps.first().role, "accounting_officer")

    def test_rejection_stops_the_chain_immediately(self):
        position = self._propose()
        submit_for_approval(position)
        decide_step(position, decision=PositionApprovalStep.Decision.REJECTED, comment="wrong grade")
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.REJECTED)
        self.assertEqual(position.approval_steps.count(), 1)

    def test_decide_step_on_a_draft_position_raises(self):
        position = self._propose()
        with self.assertRaises(ApprovalError):
            decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)

    def test_decide_step_on_an_already_approved_position_raises(self):
        position = self._propose()
        submit_for_approval(position)
        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)
        decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)
        with self.assertRaises(ApprovalError):
            decide_step(position, decision=PositionApprovalStep.Decision.APPROVED)

    def test_revise_and_resubmit_keeps_post_number_and_prior_steps(self):
        position = self._propose()
        submit_for_approval(position)
        decide_step(position, decision=PositionApprovalStep.Decision.REJECTED, comment="wrong grade")
        original_post_number = position.post_number

        junior_grade = JobGrade.objects.create(
            name="Grade 2", code="G2", occupational_level=self.level
        )
        revise_and_resubmit(position, job_grade=junior_grade)
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.DRAFT)
        self.assertEqual(position.current_step, 0)
        self.assertEqual(position.post_number, original_post_number)
        self.assertEqual(position.job_grade, junior_grade)
        self.assertEqual(position.approval_steps.count(), 1)  # the rejection stays on record

    def test_revise_and_resubmit_from_a_non_rejected_position_raises(self):
        position = self._propose()
        with self.assertRaises(ApprovalError):
            revise_and_resubmit(position, title="New title")

    def test_decide_step_with_an_invalid_decision_value_raises(self):
        position = self._propose()
        submit_for_approval(position)
        with self.assertRaises(ApprovalError):
            decide_step(position, decision="not_a_real_decision")
        position.refresh_from_db()
        self.assertEqual(position.status, Position.Status.IN_REVIEW)
        self.assertEqual(position.current_step, 0)
        self.assertEqual(position.approval_steps.count(), 0)


class BackfillTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def _hire(self, number):
        return Employee.objects.hire(
            employee_number=number, first_name="Backfill", last_name="Case", date_of_birth=date(1990, 1, 1),
            work_email=f"{number.lower()}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_creates_one_approved_position_per_current_employee(self):
        e1 = self._hire("E0060")
        e2 = self._hire("E0061")

        created = backfill_positions_for_current_employees()

        self.assertEqual(created, 2)
        self.assertEqual(Position.objects.count(), 2)
        e1.refresh_from_db()
        e2.refresh_from_db()
        self.assertIsNotNone(e1.current_version.position_id)
        self.assertIsNotNone(e2.current_version.position_id)
        self.assertNotEqual(e1.current_version.position_id, e2.current_version.position_id)
        for position in Position.objects.all():
            self.assertEqual(position.status, Position.Status.APPROVED)
            self.assertEqual(position.approval_steps.count(), 0)

    def test_two_employees_with_identical_role_get_separate_positions(self):
        """1:1, never shared/grouped -- a Position is one seat."""
        self._hire("E0062")
        self._hire("E0063")
        backfill_positions_for_current_employees()
        post_numbers = set(Position.objects.values_list("post_number", flat=True))
        self.assertEqual(len(post_numbers), 2)

    def test_is_idempotent(self):
        self._hire("E0064")
        first_count = backfill_positions_for_current_employees()
        second_count = backfill_positions_for_current_employees()
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)  # already-linked EmployeeVersions are skipped
        self.assertEqual(Position.objects.count(), 1)

    def test_employee_with_no_current_version_is_skipped_not_errored(self):
        """Orphan records (core_hr's own Sprint-1 data-quality case) must
        not crash the backfill."""
        Employee.objects.create(
            employee_number="E0065", first_name="Orphan", last_name="Case", date_of_birth=date(1990, 1, 1),
            work_email="orphan.case@example.com", hire_date=date(2020, 1, 1),
        )
        created = backfill_positions_for_current_employees()
        self.assertEqual(created, 0)
