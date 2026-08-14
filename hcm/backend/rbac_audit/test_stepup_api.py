from __future__ import annotations

from datetime import date

import pyotp
from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Role, RoleAssignment, StepUpGrant, TOTPDevice
from .stepup import confirm_totp_device, enroll_totp_device

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class TOTPEnrollmentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E100", first_name="Step", last_name="Up", date_of_birth=date(1990, 1, 1),
            work_email="stepup@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="stepup", password="x"),
        )
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="employee"))
        self.client.force_authenticate(user=self.employee.user)

    def test_status_before_enrollment(self):
        response = self.client.get("/api/v1/auth/totp/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"enrolled": False, "pending_confirmation": False})

    def test_enroll_returns_secret_and_provisioning_uri(self):
        response = self.client.post("/api/v1/auth/totp/enroll/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["secret"])
        self.assertIn("otpauth://totp/", response.data["provisioning_uri"])

    def test_status_pending_after_enroll_before_confirm(self):
        self.client.post("/api/v1/auth/totp/enroll/")
        response = self.client.get("/api/v1/auth/totp/status/")
        self.assertEqual(response.data, {"enrolled": False, "pending_confirmation": True})

    def test_confirm_with_valid_code_activates_device(self):
        self.client.post("/api/v1/auth/totp/enroll/")
        device = TOTPDevice.objects.get(employee=self.employee)
        code = pyotp.TOTP(device.secret).now()

        response = self.client.post("/api/v1/auth/totp/confirm/", {"code": code}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

        status_response = self.client.get("/api/v1/auth/totp/status/")
        self.assertEqual(status_response.data, {"enrolled": True, "pending_confirmation": False})

    def test_confirm_with_invalid_code_is_rejected(self):
        self.client.post("/api/v1/auth/totp/enroll/")
        response = self.client.post("/api/v1/auth/totp/confirm/", {"code": "000000"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_confirm_without_enrollment_is_rejected(self):
        response = self.client.post("/api/v1/auth/totp/confirm/", {"code": "123456"}, format="json")
        self.assertEqual(response.status_code, 400)


class StepUpRequestApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E100", first_name="Step", last_name="Up", date_of_birth=date(1990, 1, 1),
            work_email="stepup2@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="stepup2", password="x"),
        )
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="employee"))
        self.client.force_authenticate(user=self.employee.user)
        self.device = enroll_totp_device(self.employee)
        confirm_totp_device(self.employee, code=pyotp.TOTP(self.device.secret).now())

    def _code(self):
        return pyotp.TOTP(self.device.secret).now()

    def test_status_false_before_any_grant(self):
        response = self.client.get("/api/v1/auth/step-up/status/?scope=payroll_data")
        self.assertEqual(response.data, {"active": False})

    def test_request_with_valid_code_and_reason_grants_step_up(self):
        response = self.client.post(
            "/api/v1/auth/step-up/",
            {"code": self._code(), "scope": "payroll_data", "reason": "payroll_processing"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["scope"], "payroll_data")

        status_response = self.client.get("/api/v1/auth/step-up/status/?scope=payroll_data")
        self.assertEqual(status_response.data, {"active": True})

    def test_request_without_reason_detail_when_other_is_rejected(self):
        response = self.client.post(
            "/api/v1/auth/step-up/",
            {"code": self._code(), "scope": "payroll_data", "reason": "other", "reason_detail": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_request_with_wrong_code_is_rejected(self):
        response = self.client.post(
            "/api/v1/auth/step-up/",
            {"code": "000000", "scope": "payroll_data", "reason": "payroll_processing"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StepUpGrant.objects.count(), 0)

    def test_grant_is_audit_logged(self):
        from .models import AuditLogEntry

        self.client.post(
            "/api/v1/auth/step-up/",
            {"code": self._code(), "scope": "payroll_data", "reason": "payroll_processing"},
            format="json",
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(
                actor=self.employee, action=AuditLogEntry.Action.STEP_UP_GRANTED
            ).exists()
        )
