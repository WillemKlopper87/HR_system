from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AuditLogEntry, Role, RoleAssignment

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class AuthApiTests(TestCase):
    """The session login/logout/me endpoints the SPA needs, since OIDC/Entra
    SSO (ADR-004) isn't built yet — session auth against Django's own User
    model, one-to-one linked to core_hr.Employee."""

    def setUp(self):
        cache.clear()  # throttle counters (rbac_audit/throttling.py) live in the cache
        self.client = APIClient()
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E100", first_name="Login", last_name="Test", date_of_birth=date(1990, 1, 1),
            work_email="login.test@example.com", hire_date=date(2021, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="logintest", password="correct-password"),
        )
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="employee"))

    def test_csrf_endpoint_sets_cookie(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

    def test_login_with_valid_credentials_returns_identity_and_roles(self):
        response = self.client.post(
            "/api/v1/auth/login/", {"username": "logintest", "password": "correct-password"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["employee_number"], "E100")
        self.assertIn("employee", response.data["roles"])

    def test_login_is_audited(self):
        self.client.post(
            "/api/v1/auth/login/", {"username": "logintest", "password": "correct-password"}, format="json"
        )
        self.assertTrue(
            AuditLogEntry.objects.filter(actor=self.employee, action=AuditLogEntry.Action.LOGIN).exists()
        )

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(
            "/api/v1/auth/login/", {"username": "logintest", "password": "wrong"}, format="json"
        )
        self.assertEqual(response.status_code, 401)

    def test_login_for_user_with_no_employee_record_is_rejected(self):
        User.objects.create_user(username="orphanuser", password="x")
        response = self.client.post(
            "/api/v1/auth/login/", {"username": "orphanuser", "password": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_me_requires_authentication(self):
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 403)

    def test_me_returns_identity_when_authenticated(self):
        self.client.force_authenticate(user=self.employee.user)
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["employee_number"], "E100")

    def test_logout_ends_session(self):
        self.client.force_authenticate(user=self.employee.user)
        response = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, 200)

    def test_mutating_request_without_csrf_token_is_rejected_once_session_authenticated(self):
        # force_authenticate bypasses SessionAuthentication (and its CSRF
        # check) entirely, so this needs a real cookie-based session via
        # login() to exercise enforce_csrf.
        strict_client = APIClient(enforce_csrf_checks=True)
        strict_client.get("/api/v1/auth/csrf/")
        csrftoken = strict_client.cookies["csrftoken"].value
        strict_client.post(
            "/api/v1/auth/login/", {"username": "logintest", "password": "correct-password"},
            format="json", HTTP_X_CSRFTOKEN=csrftoken,
        )
        response = strict_client.post("/api/v1/auth/logout/")  # no X-CSRFToken header this time
        self.assertEqual(response.status_code, 403)
