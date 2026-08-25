"""Daily reminder sweep for mandatory training (C6, design spec §2.9).
Mirrors core_hr/test_reminders.py's shape (exact-offset-day matching,
not performance/reminders.py's ReminderLog-deduped range shape)."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase, override_settings
from notifications.models import Notification

from .models import Course, CourseRequirement
from .reminders import run_mandatory_training_reminders

TODAY = date(2026, 6, 1)


class MandatoryTrainingReminderFixtureMixin:
    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        # Manager sits in a different department -- the CourseRequirement
        # below is scoped to self.dept only, so the manager must NOT
        # themselves be subject to it (otherwise "employee_reminders"
        # would double-count the manager alongside their report).
        self.mgmt_dept = Department.objects.create(code="MGT", name="Management")
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=99)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.manager = Employee.objects.hire(
            employee_number="E810", first_name="Line", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="linemanager10@sentech.example.com", hire_date=date(2015, 1, 1), department=self.mgmt_dept,
            occupational_level=self.level, location=self.location,
        )
        self.report = Employee.objects.hire(
            employee_number="E811", first_name="Team", last_name="Member", date_of_birth=date(1990, 1, 1),
            work_email="teammember10@sentech.example.com", hire_date=TODAY - timedelta(days=365),
            department=self.dept, occupational_level=self.level, location=self.location, manager=self.manager,
        )
        self.course = Course.objects.create(name="Safety Induction", mandatory=True)


class MandatoryTrainingReminderTests(MandatoryTrainingReminderFixtureMixin, TestCase):
    @override_settings(MANDATORY_TRAINING_REMINDER_OFFSET_DAYS=14)
    @patch("learning.reminders.notify")
    def test_employee_reminded_on_offset_day(self, mock_notify):
        # due_within_days=104 -> due_date = hire_date(365 days ago) + 104 =
        # TODAY + (104-365)... use effective_from so subject_since=TODAY-365,
        # due_date = TODAY-365+379 = TODAY+14.
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=365),
            due_within_days=379,
        )
        with patch("learning.reminders.timezone.localdate", return_value=TODAY):
            result = run_mandatory_training_reminders()
        self.assertEqual(result["employee_reminders"], 1)
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args.kwargs["recipient"], self.report)

    @override_settings(MANDATORY_TRAINING_REMINDER_OFFSET_DAYS=14)
    @patch("learning.reminders.notify")
    def test_no_reminder_off_offset(self, mock_notify):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=365),
            due_within_days=378,  # due_date = TODAY+13, not the configured 14-day offset
        )
        with patch("learning.reminders.timezone.localdate", return_value=TODAY):
            result = run_mandatory_training_reminders()
        self.assertEqual(result["employee_reminders"], 0)
        mock_notify.assert_not_called()

    @patch("learning.reminders.notify")
    def test_manager_notified_the_day_it_lapses_into_overdue(self, mock_notify):
        # due_date == TODAY exactly -> (TODAY - due_date).days == 0.
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=365),
            due_within_days=365,
        )
        with patch("learning.reminders.timezone.localdate", return_value=TODAY):
            result = run_mandatory_training_reminders()
        self.assertEqual(result["manager_reminders"], 1)
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args.kwargs["recipient"], self.manager)

    @patch("learning.reminders.notify")
    def test_manager_not_renotified_on_a_later_day(self, mock_notify):
        # Overdue by 5 days already -- the one-time "just lapsed" event
        # already passed; no repeated daily nag.
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=365),
            due_within_days=360,
        )
        with patch("learning.reminders.timezone.localdate", return_value=TODAY):
            result = run_mandatory_training_reminders()
        self.assertEqual(result["manager_reminders"], 0)
        mock_notify.assert_not_called()

    def test_beat_schedule_registered(self):
        from django.conf import settings

        self.assertIn("run-mandatory-training-reminders-daily", settings.CELERY_BEAT_SCHEDULE)


class MandatoryTrainingReminderNotificationTests(MandatoryTrainingReminderFixtureMixin, TestCase):
    """Deliberately does NOT mock notify -- pins that `kind=
    "mandatory_training_reminder"` is a registered Notification.Kind
    member, same regression class core_hr/test_reminders.py's own
    ContractReminderNotificationTests documents for contract_reminder."""

    def test_reminder_writes_a_real_notification_with_a_registered_kind(self):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=365),
            due_within_days=365,
        )
        with patch("learning.reminders.timezone.localdate", return_value=TODAY):
            result = run_mandatory_training_reminders()
        self.assertEqual(result["manager_reminders"], 1)

        notification = Notification.objects.get(recipient=self.manager)
        self.assertEqual(notification.kind, "mandatory_training_reminder")
        self.assertIn("mandatory_training_reminder", Notification.Kind.values)
        self.assertEqual(notification.get_kind_display(), "Mandatory training reminder")

    @patch("learning.reminders.notify")
    def test_dry_run_suppresses_sends_but_still_counts(self, mock_notify):
        CourseRequirement.objects.create(
            course=self.course, department=self.dept, effective_from=TODAY - timedelta(days=365),
            due_within_days=365,
        )
        with patch("learning.reminders.timezone.localdate", return_value=TODAY):
            result = run_mandatory_training_reminders(dry_run=True)
        self.assertEqual(result["manager_reminders"], 1)
        mock_notify.assert_not_called()
        self.assertEqual(Notification.objects.count(), 0)
