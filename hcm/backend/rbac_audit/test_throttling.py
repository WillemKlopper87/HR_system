from datetime import date

import pyotp
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel

from .models import Role, RoleAssignment, StepUpGrant, TOTPDevice

User = get_user_model()


def _reference():
    dept, _ = Department.objects.get_or_create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade, _ = JobGrade.objects.get_or_create(name="Grade 1", code="G1", occupational_level=level)
    location, _ = Location.objects.get_or_create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


def _employee(username, number):
    dept, level, grade, location = _reference()
    return Employee.objects.hire(
        employee_number=number, first_name="Thr", last_name="Ottle", date_of_birth=date(1990, 1, 1),
        work_email=f"{username}@example.com", hire_date=date(2021, 1, 1), department=dept,
        occupational_level=level, job_grade=grade, location=location,
        user=User.objects.create_user(username=username, password="correct-password"),
    )


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        emp = _employee("alice", "T001")
        RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name="employee"))

    def _login(self, username, password="wrong", ip="10.0.0.1"):
        return self.client.post(
            "/api/v1/auth/login/", {"username": username, "password": password}, format="json", REMOTE_ADDR=ip
        )

    def test_eleventh_attempt_for_same_username_is_throttled_even_from_different_ips(self):
        for i in range(10):
            self.assertEqual(self._login("alice", ip=f"10.0.0.{i + 1}").status_code, 401)
        blocked = self._login("alice", password="correct-password", ip="10.0.0.99")
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_username_throttle_is_per_username(self):
        for _ in range(10):
            self._login("alice")
        self.assertEqual(self._login("bob").status_code, 401)  # different account, not throttled

    def test_username_key_is_case_insensitive(self):
        for _ in range(10):
            self._login("ALICE")
        self.assertEqual(self._login("alice").status_code, 429)

    def test_ip_burst_throttle_kicks_in(self):
        # 30/min per IP: 30 different usernames from one IP pass, the 31st is throttled
        for i in range(30):
            self.assertEqual(self._login(f"user{i}", ip="10.9.9.9").status_code, 401)
        self.assertEqual(self._login("user-last", ip="10.9.9.9").status_code, 429)
        self.assertEqual(self._login("user-last", ip="10.9.9.10").status_code, 401)


class TotpThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.employee = _employee("carol", "T002")
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="employee"))
        self.client.force_authenticate(user=self.employee.user)

    def test_sixth_wrong_confirm_code_in_a_minute_is_throttled(self):
        self.client.post("/api/v1/auth/totp/enroll/")
        for _ in range(5):
            self.assertEqual(
                self.client.post("/api/v1/auth/totp/confirm/", {"code": "000000"}, format="json").status_code, 400
            )
        # even the *correct* code is refused now — the window has to cool off
        code = pyotp.TOTP(TOTPDevice.objects.get(employee=self.employee).secret).now()
        self.assertEqual(self.client.post("/api/v1/auth/totp/confirm/", {"code": code}, format="json").status_code, 429)

    def test_step_up_challenge_is_throttled_per_user_not_globally(self):
        self.client.post("/api/v1/auth/totp/enroll/")
        device = TOTPDevice.objects.get(employee=self.employee)
        self.client.post("/api/v1/auth/totp/confirm/", {"code": pyotp.TOTP(device.secret).now()}, format="json")
        cache.clear()  # the confirm above consumed one slot; start the challenge count clean
        payload = {"code": "000000", "scope": StepUpGrant.Scope.PAYROLL_DATA, "reason": StepUpGrant.Reason.PAYROLL_PROCESSING}
        for _ in range(5):
            self.assertEqual(self.client.post("/api/v1/auth/step-up/", payload, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/v1/auth/step-up/", payload, format="json").status_code, 429)

        # another user is unaffected
        other = _employee("dave", "T003")
        RoleAssignment.objects.create(employee=other, role=Role.objects.get(name="employee"))
        other_client = APIClient()
        other_client.force_authenticate(user=other.user)
        other_client.post("/api/v1/auth/totp/enroll/")
        self.assertEqual(other_client.post("/api/v1/auth/step-up/", payload, format="json").status_code, 400)
