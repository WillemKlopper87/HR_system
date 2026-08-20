from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from rbac_audit.models import Role, RoleAssignment

from .contract_reminders import run_contract_reminders
from .models import ContractRenewalDecision, Department, Employee, EmployeeVersion, Location, OccupationalLevel


class ContractRemindersTests(TestCase):
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

    def _hire_fixed_term(self, *, number, end_date, manager=None):
        return Employee.objects.hire(
            employee_number=number, first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email=f"{number.lower()}@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=end_date, manager=manager or self.manager,
        )

    @override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=[30], CONTRACT_ESCALATION_DAYS=14)
    @patch("core_hr.contract_reminders.notify")
    def test_manager_reminded_on_offset_day(self, mock_notify):
        today = date(2026, 6, 1)
        self._hire_fixed_term(number="E900", end_date=today + timedelta(days=30))
        with patch("core_hr.contract_reminders.timezone.localdate", return_value=today):
            result = run_contract_reminders()
        self.assertEqual(result["manager_reminders"], 1)
        mock_notify.assert_called_once()
        self.assertEqual(mock_notify.call_args.kwargs["recipient"], self.manager)

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

    def test_beat_schedule_registered(self):
        from django.conf import settings

        self.assertIn("run-contract-reminders-daily", settings.CELERY_BEAT_SCHEDULE)
