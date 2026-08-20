from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from notifications.models import Notification
from rbac_audit.models import Role, RoleAssignment

from .contract_reminders import run_contract_reminders
from .models import ContractRenewalDecision, Department, Employee, EmployeeVersion, Location, OccupationalLevel

# Sentinel distinguishing "no manager kwarg passed" (fall back to
# self.manager) from an explicit manager=None (a genuinely manager-less
# employee) -- `manager or self.manager` can't tell these apart since
# None is falsy.
_UNSET = object()


class ContractReminderFixtureMixin:
    """Shared fixture for both reminder test classes below (mixin rather
    than a base TestCase, so subclassing doesn't re-run the parent's
    tests)."""

    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        # order=3 collides with the "PQ" level seeded by
        # 0002_seed_occupational_levels.py (order is unique) -- use a high
        # unused value instead, same fix as core_hr/tests.py's other
        # illustrative fixtures.
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=99)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.manager = Employee.objects.hire(
            employee_number="E800", first_name="Line", last_name="Manager",
            date_of_birth=date(1980, 1, 1), work_email="linemanager4@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.hr_admin = Employee.objects.hire(
            employee_number="E801", first_name="HR", last_name="Admin",
            date_of_birth=date(1980, 1, 1), work_email="hradmin4@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        # Role/RoleAssignment field names below are the shape used throughout
        # this codebase's other test fixtures (e.g. establishment/tests.py) --
        # confirm against one of those before trusting verbatim.
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

    def _hire_fixed_term(self, *, number, end_date, manager=_UNSET):
        # manager omitted -> defaults to self.manager; manager=None ->
        # genuinely manager-less employee (see _UNSET above).
        if manager is _UNSET:
            manager = self.manager
        return Employee.objects.hire(
            employee_number=number, first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email=f"{number.lower()}@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=end_date, manager=manager,
        )


class ContractRemindersTests(ContractReminderFixtureMixin, TestCase):
    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_manager_reminded_on_offset_day(self, mock_notify, mock_notify_many):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=30))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 1)
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args.kwargs["recipient"], self.manager)
        # Rule 4 negative case: no decision row yet and days_remaining (30)
        # is above CONTRACT_ESCALATION_DAYS (14) -- hr_admin must NOT be
        # escalated to yet.
        self.assertEqual(result["hr_admin_reminders"], 0)
        mock_notify_many.assert_not_called()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify")
    def test_no_reminder_off_offset(self, mock_notify):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=29))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 0)
        mock_notify.assert_not_called()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[14], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_hr_admin_escalation_when_no_recommendation(self, mock_notify, mock_notify_many):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=14))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["hr_admin_reminders"], 1)
        mock_notify_many.assert_called_once()
        self.assertEqual(list(mock_notify_many.call_args.args[0]), [self.hr_admin])

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_manager_not_reminded_once_recommendation_exists(self, mock_notify, mock_notify_many):
        today = date(2026, 6, 1)
        employee = self._hire_fixed_term(number="E900", end_date=today + timedelta(days=30))
        ContractRenewalDecision.objects.create(
            employee_version=employee.current_version, status=ContractRenewalDecision.Status.RECOMMENDED,
        )
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 0)
        self.assertEqual(result["hr_admin_reminders"], 1)
        mock_notify.assert_not_called()
        mock_notify_many.assert_called_once()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_no_reminders_once_decided(self, mock_notify, mock_notify_many):
        today = date(2026, 6, 1)
        employee = self._hire_fixed_term(number="E900", end_date=today + timedelta(days=30))
        ContractRenewalDecision.objects.create(
            employee_version=employee.current_version, status=ContractRenewalDecision.Status.DECIDED,
            decided_action=ContractRenewalDecision.Action.CONVERT_PERMANENT,
        )
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 0)
        self.assertEqual(result["hr_admin_reminders"], 0)
        mock_notify.assert_not_called()
        mock_notify_many.assert_not_called()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[14], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_hr_admin_reminders_zero_when_no_hr_admin_assigned(self, mock_notify, mock_notify_many):
        # No reachable hr_admin recipient -- the count must reflect actual
        # sends, not events that were computed but never delivered.
        RoleAssignment.objects.filter(employee=self.hr_admin).delete()
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=14))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["hr_admin_reminders"], 0)
        mock_notify_many.assert_not_called()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[14], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_no_manager_no_crash_and_hr_admin_still_escalates(self, mock_notify, mock_notify_many):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=14), manager=None)
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 0)
        mock_notify.assert_not_called()
        self.assertEqual(result["hr_admin_reminders"], 1)
        mock_notify_many.assert_called_once()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[20], CONTRACT_ESCALATION_DAYS=20)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_escalation_days_setting_is_honoured_at_boundary(self, mock_notify, mock_notify_many):
        # Neither offset (20) nor escalation (20) is the production default
        # (14) -- proves CONTRACT_ESCALATION_DAYS is actually read, not a
        # hardcoded 14 that happens to match every other test's override.
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=20))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["hr_admin_reminders"], 1)
        mock_notify_many.assert_called_once()

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[20], CONTRACT_ESCALATION_DAYS=19)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_escalation_days_setting_prevents_escalation_below_threshold(self, mock_notify, mock_notify_many):
        # Same days_remaining (20) as the boundary test above; only
        # CONTRACT_ESCALATION_DAYS moved (20 -> 19). The outcome flips
        # solely because of that setting, proving it drives the behavior.
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=20))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 1)
        self.assertEqual(result["hr_admin_reminders"], 0)
        mock_notify_many.assert_not_called()

    def test_beat_schedule_registered(self):
        from django.conf import settings

        self.assertIn("run-contract-reminders-daily", settings.CELERY_BEAT_SCHEDULE)


class ContractReminderNotificationTests(ContractReminderFixtureMixin, TestCase):
    """Every other test in this module mocks `notify`/`notify_many`
    outright, so no real `Notification` row is ever constructed — which is
    exactly why Task 4's suite could not catch the final review's finding
    that `kind="contract_reminder"` was not a registered
    `Notification.Kind` member at all. Django does not validate `choices`
    on save, so the value wrote silently and `get_kind_display()` fell
    back to the raw slug in `__str__`, Django admin, and
    `NotificationSerializer.kind_display`. These tests deliberately do NOT
    mock, closing that gap."""

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[14], CONTRACT_ESCALATION_DAYS=14)
    def test_reminder_writes_a_real_notification_with_a_registered_kind(self):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=14))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 1)
        self.assertEqual(result["hr_admin_reminders"], 1)

        # Both call sites (notify -> manager, notify_many -> hr_admin).
        manager_notification = Notification.objects.get(recipient=self.manager)
        hr_admin_notification = Notification.objects.get(recipient=self.hr_admin)
        for notification in (manager_notification, hr_admin_notification):
            self.assertEqual(notification.kind, "contract_reminder")
            self.assertIn("contract_reminder", Notification.Kind.values)
            self.assertEqual(notification.get_kind_display(), "Contract expiry reminder")

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[14], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify_many")
    @patch("core_hr.contract_reminders.notify")
    def test_dry_run_suppresses_sends_but_still_counts(self, mock_notify, mock_notify_many):
        # dry_run is a parameter on the Celery task's public signature
        # (tasks.py) — an operator will reach for it during an incident, so
        # "sends nothing, still reports accurate counts" needs to be
        # pinned, not assumed.
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=14))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders(dry_run=True)
        self.assertEqual(result["manager_reminders"], 1)
        self.assertEqual(result["hr_admin_reminders"], 1)
        mock_notify.assert_not_called()
        mock_notify_many.assert_not_called()
        self.assertEqual(Notification.objects.count(), 0)
