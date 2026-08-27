from datetime import date
from unittest.mock import patch

from core_hr.models import Department, Employee, EmployeeVersion, Location, OccupationalLevel
from django.conf import settings
from django.test import TestCase, override_settings
from notifications.models import Notification
from rbac_audit.models import Role, RoleAssignment

from .models import EEReport
from .reminders import run_ee_statutory_reminders
from .tasks import run_ee_statutory_reminders_task


class EEStatutoryReminderFixtureMixin:
    def setUp(self):
        dept = Department.objects.create(code="ENG", name="Engineering")
        level = OccupationalLevel.objects.create(code="P", name="Professional", order=99)
        location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.hr_admin = Employee.objects.hire(
            employee_number="E810", first_name="HR", last_name="Admin",
            date_of_birth=date(1980, 1, 1), work_email="hradmin5@sentech.example.com",
            hire_date=date(2020, 1, 1), department=dept, occupational_level=level,
            location=location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.ee_manager = Employee.objects.hire(
            employee_number="E811", first_name="EE", last_name="Manager",
            date_of_birth=date(1980, 1, 1), work_email="eemanager5@sentech.example.com",
            hire_date=date(2020, 1, 1), department=dept, occupational_level=level,
            location=location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))
        RoleAssignment.objects.create(employee=self.ee_manager, role=Role.objects.get(name="ee_manager"))

    def _report(self, *, form_type, report_year, status):
        return EEReport.objects.create(
            form_type=form_type, report_year=report_year, version=1,
            period_start=date(report_year, 1, 1), period_end=date(report_year, 12, 31),
            status=status, data={},
        )


class EEStatutoryReminderTests(EEStatutoryReminderFixtureMixin, TestCase):
    @override_settings(EE_STATUTORY_REMINDER_OFFSETS_DAYS=[30])
    @patch("ee_reporting.reminders.notify_many")
    def test_eea14_reminder_fires_on_offset_day(self, mock_notify_many):
        # Last weekday of Aug 2026 is Monday 31 Aug 2026; 30 days before is 1 Aug 2026.
        today = date(2026, 8, 1)
        result = run_ee_statutory_reminders(today=today)
        self.assertEqual(result["eea14_reminders"], 1)
        mock_notify_many.assert_called_once()
        recipients = set(mock_notify_many.call_args.args[0])
        self.assertEqual(recipients, {self.hr_admin, self.ee_manager})
        self.assertEqual(mock_notify_many.call_args.kwargs["kind"], "ee_statutory_reminder")

    @override_settings(EE_STATUTORY_REMINDER_OFFSETS_DAYS=[30])
    @patch("ee_reporting.reminders.notify_many")
    def test_online_report_reminder_fires_when_reports_outstanding(self, mock_notify_many):
        # Jan 15 2027 minus 30 days = 16 Dec 2026. Nothing signed off for report_year 2026.
        today = date(2026, 12, 16)
        result = run_ee_statutory_reminders(today=today)
        self.assertEqual(result["online_report_reminders"], 1)
        mock_notify_many.assert_called_once()
        self.assertIn("2026", mock_notify_many.call_args.kwargs["body"])
        self.assertIn("EEA2", mock_notify_many.call_args.kwargs["body"])
        self.assertIn("EEA4", mock_notify_many.call_args.kwargs["body"])

    @override_settings(EE_STATUTORY_REMINDER_OFFSETS_DAYS=[30])
    @patch("ee_reporting.reminders.notify_many")
    def test_online_report_reminder_silent_once_both_forms_signed_off(self, mock_notify_many):
        self._report(form_type=EEReport.FormType.EEA2, report_year=2026, status=EEReport.Status.SIGNED_OFF)
        self._report(form_type=EEReport.FormType.EEA4, report_year=2026, status=EEReport.Status.SIGNED_OFF)
        today = date(2026, 12, 16)
        result = run_ee_statutory_reminders(today=today)
        self.assertEqual(result["online_report_reminders"], 0)
        mock_notify_many.assert_not_called()

    @override_settings(EE_STATUTORY_REMINDER_OFFSETS_DAYS=[30])
    @patch("ee_reporting.reminders.notify_many")
    def test_no_reminder_off_offset_day(self, mock_notify_many):
        result = run_ee_statutory_reminders(today=date(2026, 5, 1))
        self.assertEqual(result, {"online_report_reminders": 0, "eea14_reminders": 0})
        mock_notify_many.assert_not_called()

    def test_dry_run_counts_without_notifying(self):
        with patch("ee_reporting.reminders.notify_many") as mock_notify_many:
            with override_settings(EE_STATUTORY_REMINDER_OFFSETS_DAYS=[30]):
                result = run_ee_statutory_reminders(dry_run=True, today=date(2026, 8, 1))
        self.assertEqual(result["eea14_reminders"], 1)
        mock_notify_many.assert_not_called()

    def test_beat_schedule_registered(self):
        self.assertIn("run-ee-statutory-reminders-daily", settings.CELERY_BEAT_SCHEDULE)


class EEStatutoryReminderNotificationTests(EEStatutoryReminderFixtureMixin, TestCase):
    """Deliberately does NOT mock notify_many — pins that
    kind="ee_statutory_reminder" is a registered Notification.Kind member,
    same regression class core_hr/test_reminders.py and
    learning/test_reminders.py document for their own reminder kinds."""

    def test_reminder_writes_a_real_notification_with_a_registered_kind(self):
        result = run_ee_statutory_reminders(today=date(2026, 8, 1))
        self.assertEqual(result["eea14_reminders"], 1)
        notification = Notification.objects.get(recipient=self.hr_admin)
        self.assertEqual(notification.kind, "ee_statutory_reminder")
        self.assertEqual(notification.get_kind_display(), "EE statutory deadline reminder")

    def test_task_runs_synchronously(self):
        result = run_ee_statutory_reminders_task.apply(kwargs={"dry_run": True}).get()
        self.assertIn("online_report_reminders", result)
        self.assertIn("eea14_reminders", result)
