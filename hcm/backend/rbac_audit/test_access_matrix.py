"""Golden role x endpoint access matrix (H2 — RBAC-Roles.md "penetration-style"
sweep, made permanent).

For every router-registered endpoint and every seeded demo role, we assert the
exact (list GET, empty-body POST) status pair. The values were generated
against the real seeded system, reviewed line by line against RBAC-Roles.md,
and frozen here — so a future permission change that widens or narrows access
anywhere fails loudly and has to be reviewed on purpose, and a viewset that
crashes on a bare POST (500) can never come back.

Reading the pairs: 200 = may list; 403 = role denied; 400 = POST reached the
serializer (write allowed by role, payload invalid); 405 = create explicitly
disabled (mutations go through named actions or a service); 201 = created
from an empty payload (employer-config only: hr_admin, every field blank-able).

Every role holds a payroll StepUpGrant during the sweep so this measures the
*role* gate, not the ADR-009 MFA gate (which has its own tests).

Two defects this sweep found and fixed on the day it was written:
- EEReportViewSet kept "post" for its actions without disabling create() ->
  bare POST reached an all-read-only serializer -> 500 IntegrityError; now 405.
- RemunerationRecordViewSet used the coarse EEReportingPermission, so
  ee_manager and accounting_officer could list raw per-employee remuneration
  (behind step-up they could self-enrol) — RBAC-Roles.md says neither has pay
  access. Now RemunerationRecordPermission: hr_admin RW, auditor R.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import StepUpGrant

User = get_user_model()

ROLE_USERS = ["hradmin", "manager", "recruiter", "compmanager", "eemanager", "accountingofficer", "employee"]

# endpoint -> (GET list, POST {}) per user in ROLE_USERS order
EXPECTED = {
    "applicants": ("200/400", "403/403", "200/400", "403/403", "403/403", "403/403", "403/403"),

    "assessment-assignments": ("200/400", "200/403", "200/400", "200/403", "200/400", "200/403", "200/403"),

    "benefits": ("200/400", "200/403", "200/403", "200/400", "200/403", "200/403", "200/403"),

    "benefits-elections": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "biometric-enrollments": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "certifications": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "comp-proposals": ("200/400", "403/403", "403/403", "200/400", "403/403", "403/403", "403/403"),

    "data-quality-exceptions": ("200/405", "403/403", "403/403", "403/403", "403/403", "403/403", "403/403"),

    "departments": ("200/400", "200/403", "200/403", "200/403", "200/403", "200/403", "200/403"),

    "ee-plans": ("200/400", "403/403", "403/403", "403/403", "200/400", "200/400", "403/403"),

    "ee-questionnaires": ("200/400", "403/403", "403/403", "403/403", "200/400", "200/400", "403/403"),

    "ee-reports": ("200/405", "403/403", "403/403", "403/403", "200/405", "200/405", "403/403"),

    "ee-sectors": ("200/405", "403/403", "403/403", "403/403", "200/405", "200/405", "403/403"),

    "employee-skills": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "employee-versions": ("200/405", "200/405", "200/405", "200/405", "200/405", "200/405", "200/405"),

    "employees": ("200/405", "200/405", "200/405", "200/405", "200/405", "200/405", "200/405"),

    "employer-config": ("200/201", "403/403", "403/403", "403/403", "200/403", "200/403", "403/403"),

    "feedback": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "goals": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "job-grades": ("200/400", "200/403", "200/403", "200/403", "200/403", "200/403", "200/403"),

    "liveness-checks": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "locations": ("200/400", "200/403", "200/403", "200/403", "200/403", "200/403", "200/403"),

    "occupational-levels": ("200/405", "200/405", "200/405", "200/405", "200/405", "200/405", "200/405"),

    "offers": ("200/400", "403/403", "200/400", "403/403", "403/403", "403/403", "403/403"),

    "pay-bands": ("200/400", "403/403", "403/403", "200/400", "403/403", "403/403", "403/403"),

    "policies": ("200/400", "200/403", "200/403", "200/403", "200/403", "200/403", "200/403"),

    "probation-periods": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "probation-reviews": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "policy-acknowledgments": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),

    "provider-configs": ("200/400", "403/403", "403/403", "403/403", "403/403", "403/403", "403/403"),

    "remuneration-records": ("200/400", "403/403", "403/403", "403/403", "403/403", "403/403", "403/403"),

    "requisitions": ("200/400", "403/403", "200/400", "403/403", "403/403", "403/403", "403/403"),

    "review-cycles": ("200/400", "200/403", "200/403", "200/403", "200/403", "200/403", "200/403"),

    "reviews": ("200/405", "200/405", "200/405", "200/405", "200/405", "200/405", "200/405"),

    "skills": ("200/400", "200/403", "200/403", "200/403", "200/403", "200/403", "200/403"),

    "training-records": ("200/400", "200/400", "200/400", "200/400", "200/400", "200/400", "200/400"),
}


class AccessMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cache.clear()
        call_command("seed_demo_data", verbosity=0)
        cls.clients = {}
        for username in ROLE_USERS:
            user = User.objects.get(username=username)
            StepUpGrant.objects.create(
                employee=user.employee,
                scope=StepUpGrant.Scope.PAYROLL_DATA,
                reason=StepUpGrant.Reason.PAYROLL_PROCESSING,
                expires_at=timezone.now() + timedelta(minutes=15),
            )
            client = APIClient()
            client.force_authenticate(user=user)
            cls.clients[username] = client

    def test_every_endpoint_matches_the_reviewed_matrix(self):
        actual = {}
        for endpoint in EXPECTED:
            row = []
            for username in ROLE_USERS:
                client = self.clients[username]
                get = client.get(f"/api/v1/{endpoint}/").status_code
                post = client.post(f"/api/v1/{endpoint}/", {}, format="json").status_code
                row.append(f"{get}/{post}")
            actual[endpoint] = tuple(row)
        diffs = []
        for endpoint, expected in EXPECTED.items():
            if actual[endpoint] != expected:
                diffs.append(f"{endpoint}: expected {expected} got {actual[endpoint]}")
        self.assertEqual(
            diffs, [], "\n".join(["Access matrix drifted (roles: " + ", ".join(ROLE_USERS) + "):"] + diffs)
        )

    def test_no_endpoint_ever_returns_500_to_a_bare_post(self):
        for endpoint in EXPECTED:
            for username in ROLE_USERS:
                status = self.clients[username].post(f"/api/v1/{endpoint}/", {}, format="json").status_code
                self.assertLess(status, 500, f"{username} POST /{endpoint}/ -> {status}")

    def test_restricted_payroll_endpoints_are_closed_to_non_payroll_roles(self):
        # RBAC-Roles.md: R (Restricted) read only for hr_admin, comp_manager, auditor;
        # ee_manager "no pay access"; accounting_officer no standing S/R access.
        for endpoint in ("pay-bands", "comp-proposals", "remuneration-records"):
            for username in ("manager", "recruiter", "eemanager", "accountingofficer", "employee"):
                self.assertEqual(
                    self.clients[username].get(f"/api/v1/{endpoint}/").status_code, 403, f"{username} GET /{endpoint}/"
                )
