from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .models import Feedback, Review, ReviewCycle
from .services import classify_feedback_type, close_review_cycle, launch_review_cycle


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class ReviewCycleLaunchTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.manager = Employee.objects.hire(
            employee_number="MGR", first_name="Mandy", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="mgr@example.com", hire_date=date(2015, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location,
        )
        self.report = Employee.objects.hire(
            employee_number="E100", first_name="Rep", last_name="Ort", date_of_birth=date(1995, 1, 1),
            work_email="rep@example.com", hire_date=date(2020, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location, manager=self.manager,
        )
        self.cycle = ReviewCycle.objects.create(name="2026 Annual", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))

    def test_launch_creates_one_review_per_active_employee_with_manager_snapshotted(self):
        created = launch_review_cycle(self.cycle)
        self.assertEqual(created, 2)
        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, ReviewCycle.Status.LAUNCHED)
        self.assertIsNotNone(self.cycle.launched_at)

        review = Review.objects.get(review_cycle=self.cycle, employee=self.report)
        self.assertEqual(review.manager, self.manager)

    def test_launch_is_idempotent(self):
        launch_review_cycle(self.cycle)
        self.cycle.refresh_from_db()
        self.cycle.status = ReviewCycle.Status.DRAFT
        self.cycle.save(update_fields=["status"])
        second_count = launch_review_cycle(self.cycle)
        self.assertEqual(second_count, 0)
        self.assertEqual(Review.objects.filter(review_cycle=self.cycle).count(), 2)

    def test_cannot_launch_a_non_draft_cycle(self):
        launch_review_cycle(self.cycle)
        with self.assertRaises(ValueError):
            launch_review_cycle(self.cycle)

    def test_terminated_employee_excluded_from_launch(self):
        from core_hr.models import EmploymentEvent

        self.report.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.TERMINATION, effective_date=date(2025, 12, 31)
        )
        created = launch_review_cycle(self.cycle)
        self.assertEqual(created, 1)  # manager only
        self.assertFalse(Review.objects.filter(review_cycle=self.cycle, employee=self.report).exists())

    def test_close_requires_launched_status(self):
        with self.assertRaises(ValueError):
            close_review_cycle(self.cycle)
        launch_review_cycle(self.cycle)
        self.cycle.refresh_from_db()
        close_review_cycle(self.cycle)
        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, ReviewCycle.Status.CLOSED)


class ReviewCompletionStatusTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E200", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="e200@example.com", hire_date=date(2021, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location,
        )
        cycle = ReviewCycle.objects.create(name="Cycle", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.review = Review.objects.create(review_cycle=cycle, employee=self.employee)

    def test_not_started_by_default(self):
        self.assertEqual(self.review.completion_status, "not_started")

    def test_self_submitted_only(self):
        from django.utils import timezone

        self.review.self_submitted_at = timezone.now()
        self.review.save()
        self.assertEqual(self.review.completion_status, "self_submitted")

    def test_completed_when_both_submitted(self):
        from django.utils import timezone

        self.review.self_submitted_at = timezone.now()
        self.review.manager_submitted_at = timezone.now()
        self.review.save()
        self.assertEqual(self.review.completion_status, "completed")


class FeedbackClassificationTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.manager = Employee.objects.hire(
            employee_number="MGR", first_name="Mandy", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="mgr@example.com", hire_date=date(2015, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location,
        )
        self.report = Employee.objects.hire(
            employee_number="E100", first_name="Rep", last_name="Ort", date_of_birth=date(1995, 1, 1),
            work_email="rep@example.com", hire_date=date(2020, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location, manager=self.manager,
        )
        self.peer = Employee.objects.hire(
            employee_number="PEER", first_name="Pee", last_name="Rr", date_of_birth=date(1993, 1, 1),
            work_email="peer@example.com", hire_date=date(2020, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location,
        )

    def test_manager_in_reporting_chain_is_classified_as_manager_feedback(self):
        self.assertEqual(classify_feedback_type(self.manager, self.report), Feedback.FeedbackType.MANAGER)

    def test_unrelated_employee_is_classified_as_peer_feedback(self):
        self.assertEqual(classify_feedback_type(self.peer, self.report), Feedback.FeedbackType.PEER)

    def test_no_author_defaults_to_peer(self):
        self.assertEqual(classify_feedback_type(None, self.report), Feedback.FeedbackType.PEER)
