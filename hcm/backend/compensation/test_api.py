from __future__ import annotations

from datetime import date
from decimal import Decimal

import pyotp
from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from ee_reporting.models import RemunerationRecord
from rbac_audit.models import Role, RoleAssignment
from rbac_audit.stepup import confirm_totp_device, enroll_totp_device, request_step_up
from rest_framework.test import APIClient

from .models import Benefit, BenefitsElection, CompCycle, CompProposal, PayBand

User = get_user_model()


def _grant_payroll_step_up(employee):
    """PayBand/CompProposal are Restricted-tier (Data-Dictionary.md) and
    now require an active StepUpGrant on top of the comp_manager/hr_admin
    role check — every existing test that exercises those endpoints as a
    legitimately-privileged user needs one, or it 403s for a step-up
    reason instead of the thing the test actually means to check."""
    device = enroll_totp_device(employee)
    confirm_totp_device(employee, code=pyotp.TOTP(device.secret).now())
    request_step_up(
        employee, code=pyotp.TOTP(device.secret).now(), scope="payroll_data", reason="payroll_processing",
    )


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class CompensationApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        self.comp_manager = Employee.objects.hire(
            employee_number="C001", first_name="Cara", last_name="CompManager", date_of_birth=date(1985, 1, 1),
            work_email="cara@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="cara", password="x"),
        )
        RoleAssignment.objects.create(employee=self.comp_manager, role=Role.objects.get(name="comp_manager"))

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1980, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2018, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="hradmin", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.line_manager = Employee.objects.hire(
            employee_number="M001", first_name="Manny", last_name="Manager", date_of_birth=date(1982, 1, 1),
            work_email="manny@example.com", hire_date=date(2019, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="manny", password="x"),
        )
        RoleAssignment.objects.create(employee=self.line_manager, role=Role.objects.get(name="line_manager"))

        self.plain_employee = Employee.objects.hire(
            employee_number="E100", first_name="Plain", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="plain@example.com", hire_date=date(2021, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="plain", password="x"),
        )

        self.pay_band = PayBand.objects.create(
            job_grade=self.grade, min_salary=300000, mid_salary=400000, max_salary=500000, valid_from=date(2020, 1, 1)
        )

        _grant_payroll_step_up(self.comp_manager)
        _grant_payroll_step_up(self.hr_admin)


class ModuleWidePermissionTests(CompensationApiTestCase):
    """Sprint 10 acceptance criterion: 'Pay-data visibility restricted to
    comp manager/HR admin roles only (strict RBAC)' — still true for pay
    bands and comp proposals, genuine pay figures. Sprint 15 (ESS) opens
    the benefits catalog and elections to self-service — see
    BenefitsSelfServiceApiTests below for that surface's own tests."""

    def test_line_manager_cannot_view_pay_bands(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get("/api/v1/pay-bands/")
        self.assertEqual(response.status_code, 403)

    def test_plain_employee_cannot_view_comp_proposals(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/comp-proposals/")
        self.assertEqual(response.status_code, 403)

    def test_plain_employee_can_view_but_not_write_benefits_catalog(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/benefits/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/v1/benefits/", {"name": "New Benefit"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_plain_employee_sees_only_own_benefits_elections(self):
        benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)
        BenefitsElection.objects.create(
            employee=self.plain_employee, benefit=benefit, status=BenefitsElection.Status.ENROLLED
        )
        other_benefit = Benefit.objects.create(name="Retirement Fund", category=Benefit.Category.RETIREMENT)
        BenefitsElection.objects.create(
            employee=self.line_manager, benefit=other_benefit, status=BenefitsElection.Status.ENROLLED
        )
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/benefits-elections/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["employee"], self.plain_employee.id)

    def test_comp_proposal_list_includes_minimal_employee_display(self):
        CompProposal.objects.create(
            employee=self.plain_employee,
            current_job_grade=self.grade,
            proposed_annual_salary=Decimal("420000.00"),
            proposed_by=self.comp_manager,
        )
        self.client.force_authenticate(user=self.comp_manager.user)

        response = self.client.get("/api/v1/comp-proposals/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["results"][0]["employee_display"],
            f"{self.plain_employee.employee_number} — {self.plain_employee.first_name} {self.plain_employee.last_name}",
        )

    def test_comp_manager_can_view_all_endpoints(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        for path in ("/api/v1/pay-bands/", "/api/v1/comp-proposals/", "/api/v1/benefits/", "/api/v1/benefits-elections/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, f"{path}: {response.data}")

    def test_hr_admin_can_view_all_endpoints(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        for path in ("/api/v1/pay-bands/", "/api/v1/comp-proposals/", "/api/v1/benefits/", "/api/v1/benefits-elections/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, f"{path}: {response.data}")

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/v1/pay-bands/")
        self.assertIn(response.status_code, (401, 403))


class PayBandApiTests(CompensationApiTestCase):
    def test_comp_manager_can_create_pay_band(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        other_grade = JobGrade.objects.create(name="Grade 2", code="G2", occupational_level=self.level)
        response = self.client.post(
            "/api/v1/pay-bands/",
            {
                "job_grade": other_grade.id, "min_salary": "200000", "mid_salary": "300000",
                "max_salary": "400000", "valid_from": "2024-01-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created_by"], self.comp_manager.id)

    def test_min_mid_max_ordering_is_validated_at_the_api_layer(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/pay-bands/",
            {
                "job_grade": self.grade.id, "min_salary": "500000", "mid_salary": "300000",
                "max_salary": "400000", "valid_from": "2024-01-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class CompProposalWorkflowApiTests(CompensationApiTestCase):
    def setUp(self):
        super().setUp()
        self.employee = self.plain_employee

    def test_comp_manager_can_propose_a_change(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.employee.id, "proposed_annual_salary": "999999", "justification": "market adjustment"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["requires_override"])
        self.assertEqual(response.data["proposed_by"], self.comp_manager.id)
        self.assertEqual(response.data["current_job_grade"], self.grade.id)

    def test_client_supplied_status_and_current_job_grade_are_ignored_on_create(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        other_grade = JobGrade.objects.create(name="Grade 2", code="G2", occupational_level=self.level)
        response = self.client.post(
            "/api/v1/comp-proposals/",
            {
                "employee": self.employee.id, "proposed_annual_salary": "350000",
                "status": "approved", "current_job_grade": other_grade.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "proposed")
        self.assertEqual(response.data["current_job_grade"], self.grade.id)

    def test_proposer_cannot_approve_own_proposal(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        create = self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.employee.id, "proposed_annual_salary": "350000"},
            format="json",
        )
        proposal_id = create.data["id"]
        response = self.client.post(f"/api/v1/comp-proposals/{proposal_id}/approve/")
        self.assertEqual(response.status_code, 400)

    def test_different_comp_manager_or_hr_admin_can_approve(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade, proposed_annual_salary=350000,
            requires_override=False, proposed_by=self.comp_manager,
        )
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/comp-proposals/{proposal.id}/approve/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "approved")
        self.assertEqual(response.data["approved_by"], self.hr_admin.id)

    def test_out_of_band_approval_without_override_reason_is_rejected(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade, proposed_annual_salary=999999,
            requires_override=True, proposed_by=self.comp_manager,
        )
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/comp-proposals/{proposal.id}/approve/")
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            f"/api/v1/comp-proposals/{proposal.id}/approve/", {"override_reason": "market adjustment"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["override_reason"], "market adjustment")

    def test_reject_endpoint(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade, proposed_annual_salary=350000,
            requires_override=False, proposed_by=self.comp_manager,
        )
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/comp-proposals/{proposal.id}/reject/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "rejected")


class BenefitsElectionApiTests(CompensationApiTestCase):
    def test_comp_manager_can_record_an_election(self):
        benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/benefits-elections/",
            {"employee": self.plain_employee.id, "benefit": benefit.id, "status": "enrolled"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_duplicate_election_for_same_employee_and_benefit_is_rejected(self):
        benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)
        BenefitsElection.objects.create(employee=self.plain_employee, benefit=benefit, status=BenefitsElection.Status.ENROLLED)
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/benefits-elections/",
            {"employee": self.plain_employee.id, "benefit": benefit.id, "status": "waived"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class BenefitsSelfServiceApiTests(CompensationApiTestCase):
    """Sprint 15 (ESS): an employee electing/waiving their own benefits."""

    def test_employee_can_elect_a_benefit_for_self(self):
        benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.post(
            "/api/v1/benefits-elections/",
            {"employee": self.plain_employee.id, "benefit": benefit.id, "status": "enrolled"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["employee"], self.plain_employee.id)

    def test_employee_cannot_elect_a_benefit_for_someone_else(self):
        """perform_create forces employee=requester for non-privileged
        callers — whatever employee id the client sends is ignored, not
        rejected with a 4xx, so this asserts the actual created row's
        owner rather than expecting the request to fail outright."""
        benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.post(
            "/api/v1/benefits-elections/",
            {"employee": self.line_manager.id, "benefit": benefit.id, "status": "enrolled"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["employee"], self.plain_employee.id)

    def test_employee_cannot_read_someone_elses_election_by_id(self):
        benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)
        election = BenefitsElection.objects.create(
            employee=self.line_manager, benefit=benefit, status=BenefitsElection.Status.ENROLLED
        )
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/benefits-elections/{election.id}/")
        self.assertEqual(response.status_code, 403)

    def test_employee_can_waive_their_own_election(self):
        benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)
        election = BenefitsElection.objects.create(
            employee=self.plain_employee, benefit=benefit, status=BenefitsElection.Status.ENROLLED
        )
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.patch(
            f"/api/v1/benefits-elections/{election.id}/", {"status": "waived"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "waived")


class PayrollStepUpGateApiTests(CompensationApiTestCase):
    """PayBand/CompProposal are Restricted-tier — comp_manager/hr_admin
    role alone is necessary but no longer sufficient; a live StepUpGrant
    is required too. A fresh comp_manager (no grant obtained yet, unlike
    self.comp_manager which setUp() already grants one for) proves the
    gate actually blocks, not just that the base class's setUp works
    around it."""

    def setUp(self):
        super().setUp()
        self.fresh_comp_manager = Employee.objects.hire(
            employee_number="C002", first_name="Fresh", last_name="CompManager", date_of_birth=date(1985, 1, 1),
            work_email="fresh@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="freshcompmanager", password="x"),
        )
        RoleAssignment.objects.create(employee=self.fresh_comp_manager, role=Role.objects.get(name="comp_manager"))

    def test_comp_manager_without_step_up_grant_is_blocked_from_pay_bands(self):
        self.client.force_authenticate(user=self.fresh_comp_manager.user)
        response = self.client.get("/api/v1/pay-bands/")
        self.assertEqual(response.status_code, 403)

    def test_comp_manager_without_step_up_grant_is_blocked_from_comp_proposals(self):
        self.client.force_authenticate(user=self.fresh_comp_manager.user)
        response = self.client.get("/api/v1/comp-proposals/")
        self.assertEqual(response.status_code, 403)

    def test_comp_manager_gains_access_after_obtaining_step_up_grant(self):
        self.client.force_authenticate(user=self.fresh_comp_manager.user)
        response = self.client.get("/api/v1/pay-bands/")
        self.assertEqual(response.status_code, 403)

        _grant_payroll_step_up(self.fresh_comp_manager)
        response = self.client.get("/api/v1/pay-bands/")
        self.assertEqual(response.status_code, 200)

    def test_approve_action_also_requires_step_up(self):
        proposal = CompProposal.objects.create(
            employee=self.plain_employee, current_job_grade=self.grade, proposed_annual_salary=350000,
            requires_override=False, proposed_by=self.comp_manager,
        )
        self.client.force_authenticate(user=self.fresh_comp_manager.user)
        response = self.client.post(f"/api/v1/comp-proposals/{proposal.id}/approve/")
        self.assertEqual(response.status_code, 403)

    def test_step_up_grant_is_scoped_per_employee_not_global(self):
        """self.comp_manager's grant (from the base setUp) must not leak
        access to a different comp_manager who hasn't obtained their own."""
        self.client.force_authenticate(user=self.fresh_comp_manager.user)
        response = self.client.get("/api/v1/pay-bands/")
        self.assertEqual(response.status_code, 403)


class CompCycleApiTests(CompensationApiTestCase):
    """CompCycle is Internal-tier, not Restricted -- deliberately NOT
    RequiresPayrollStepUp (design spec §6): a cycle carries no individual's
    pay figure. A comp_manager who has never obtained a step-up grant
    (self.fresh_comp_manager-equivalent -- reuse comp_manager here, which
    DOES have a grant from the base setUp, but that's incidental; the
    point under test is that CompCycle doesn't demand one at all)."""

    def setUp(self):
        super().setUp()
        self.no_stepup_comp_manager = Employee.objects.hire(
            employee_number="C003", first_name="NoStepUp", last_name="CompManager", date_of_birth=date(1985, 1, 1),
            work_email="nostepup@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="nostepup", password="x"),
        )
        RoleAssignment.objects.create(employee=self.no_stepup_comp_manager, role=Role.objects.get(name="comp_manager"))

    def test_comp_manager_without_step_up_grant_can_still_read_cycles(self):
        self.client.force_authenticate(user=self.no_stepup_comp_manager.user)
        response = self.client.get("/api/v1/comp-cycles/")
        self.assertEqual(response.status_code, 200)

    def test_comp_manager_without_step_up_grant_can_create_a_cycle(self):
        self.client.force_authenticate(user=self.no_stepup_comp_manager.user)
        response = self.client.post(
            "/api/v1/comp-cycles/",
            {
                "name": "FY2026 Annual Review", "period_start": "2026-04-01", "period_end": "2027-03-31",
                "budget_amount": "1000000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["created_by"], self.no_stepup_comp_manager.id)

    def test_plain_employee_cannot_view_or_create_cycles(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/comp-cycles/")
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            "/api/v1/comp-cycles/",
            {"name": "X", "period_start": "2026-04-01", "period_end": "2027-03-31", "budget_amount": "1000"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_open_and_close_actions(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        cycle = CompCycle.objects.create(
            name="FY2026 Annual Review", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("1000000"),
        )
        response = self.client.post(f"/api/v1/comp-cycles/{cycle.id}/open/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "open")

        response = self.client.post(f"/api/v1/comp-cycles/{cycle.id}/close/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "closed")
        self.assertIsNotNone(response.data["closed_at"])

    def test_closing_a_cycle_via_the_api_rejects_its_stragglers(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        cycle = CompCycle.objects.create(
            name="FY2026 Annual Review", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("1000000"), status=CompCycle.Status.OPEN,
        )
        proposal = CompProposal.objects.create(
            employee=self.plain_employee, current_job_grade=self.grade, proposed_annual_salary=420000, cycle=cycle,
        )
        response = self.client.post(f"/api/v1/comp-cycles/{cycle.id}/close/")
        self.assertEqual(response.status_code, 200, response.data)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "rejected")

    def test_status_field_is_not_directly_writable(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/comp-cycles/",
            {
                "name": "FY2026 Annual Review", "period_start": "2026-04-01", "period_end": "2027-03-31",
                "budget_amount": "1000000", "status": "open",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "draft")

    def test_utilization_reflects_pending_and_committed_proposals(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        cycle = CompCycle.objects.create(
            name="FY2026 Annual Review", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("1000000"), status=CompCycle.Status.OPEN,
        )
        RemunerationRecord.objects.create(
            employee=self.plain_employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=0,
        )
        response = self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.plain_employee.id, "proposed_annual_salary": "440000", "cycle": cycle.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        detail = self.client.get(f"/api/v1/comp-cycles/{cycle.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(Decimal(detail.data["utilization"]["pending_total"]), Decimal("40000"))
        self.assertEqual(detail.data["proposal_count"], 1)


class CompProposalCycleAndBonusApiTests(CompensationApiTestCase):
    def setUp(self):
        super().setUp()
        RemunerationRecord.objects.create(
            employee=self.plain_employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=0,
        )
        self.cycle = CompCycle.objects.create(
            name="FY2026 Annual Review", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("1000000"), status=CompCycle.Status.OPEN,
        )

    def test_comp_manager_can_create_a_bonus_proposal(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.plain_employee.id, "proposal_type": "bonus", "bonus_amount": "20000", "cycle": self.cycle.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["budget_impact"], "20000.00")
        self.assertIsNone(response.data["proposed_annual_salary"])

    def test_increase_proposal_in_a_cycle_snapshots_baseline(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.plain_employee.id, "proposed_annual_salary": "440000", "cycle": self.cycle.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["baseline_salary_at_proposal"], "400000.00")
        self.assertEqual(response.data["budget_impact"], "40000.00")

    def test_bonus_missing_amount_is_rejected(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.plain_employee.id, "proposal_type": "bonus"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_increase_without_a_remuneration_record_cannot_join_a_cycle(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        no_record_employee = Employee.objects.hire(
            employee_number="E200", first_name="No", last_name="Record", date_of_birth=date(1990, 1, 1),
            work_email="norecord@example.com", hire_date=date(2021, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        response = self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": no_record_employee.id, "proposed_annual_salary": "440000", "cycle": self.cycle.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_proposal_list_can_be_filtered_by_cycle(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.plain_employee.id, "proposed_annual_salary": "440000", "cycle": self.cycle.id},
            format="json",
        )
        self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.plain_employee.id, "proposed_annual_salary": "410000"},
            format="json",
        )
        response = self.client.get(f"/api/v1/comp-proposals/?cycle={self.cycle.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_proposal_serializer_carries_read_only_performance_context(self):
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.post(
            "/api/v1/comp-proposals/",
            {"employee": self.plain_employee.id, "proposed_annual_salary": "440000"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        # No scored PerformanceAgreement exists for this employee in this
        # test, so context is None -- asserting the KEY is present (never
        # an input to anything, just informational, design spec §2.8) is
        # what matters, not a specific score value here.
        self.assertIn("performance_context", response.data)
        self.assertIsNone(response.data["performance_context"])


class MyTotalRewardsApiTests(CompensationApiTestCase):
    """The load-bearing access-control decision (design spec §3): self
    only, no employee id parameter accepted at all, no privileged
    view-anyone mode, no step-up gate."""

    def setUp(self):
        super().setUp()
        self.benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)
        BenefitsElection.objects.create(
            employee=self.plain_employee, benefit=self.benefit, status=BenefitsElection.Status.ENROLLED
        )
        self.record = RemunerationRecord.objects.create(
            employee=self.plain_employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=20000,
        )
        PayBand.objects.create(
            job_grade=self.grade, min_salary=300000, mid_salary=400000, max_salary=500000, valid_from=date(2020, 1, 1)
        )

    def test_employee_sees_their_own_statement(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/my-total-rewards/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["salary"]["fixed_remuneration"], 400000)
        self.assertEqual(response.data["salary"]["total_remuneration"], 420000)
        self.assertEqual(len(response.data["benefits"]), 1)
        self.assertEqual(response.data["benefits"][0]["status"], "enrolled")

    def test_pay_band_position_is_scoped_to_the_requesters_own_grade_only(self):
        other_grade = JobGrade.objects.create(name="Grade 2", code="G2", occupational_level=self.level)
        PayBand.objects.create(
            job_grade=other_grade, min_salary=900000, mid_salary=950000, max_salary=999000, valid_from=date(2020, 1, 1)
        )
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/my-total-rewards/")
        self.assertEqual(response.status_code, 200)
        position = response.data["pay_band_position"]
        self.assertEqual(Decimal(position["min_salary"]), Decimal("300000"))
        self.assertEqual(Decimal(position["max_salary"]), Decimal("500000"))
        # The percentile is within this employee's OWN band's 0-200000
        # range: (400000-300000)/(500000-300000)*100 = 50.
        self.assertAlmostEqual(float(position["percentile"]), 50.0)

    def test_no_employee_parameter_is_accepted_to_view_someone_elses_statement(self):
        """No path/query parameter exists at all to name a different
        employee -- confirms the endpoint always resolves strictly from
        the authenticated session (design spec §3.2), not merely that a
        role check blocks it."""
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get(f"/api/v1/my-total-rewards/?employee={self.plain_employee.id}")
        self.assertEqual(response.status_code, 200, response.data)
        # The line_manager's OWN statement comes back, not the plain
        # employee's -- the query param is simply ignored.
        self.assertEqual(response.data["employee"], self.line_manager.id)

    def test_comp_manager_gets_their_own_statement_not_a_privileged_any_employee_view(self):
        """No privileged "view anyone's statement" mode exists at all
        (design spec §3.4) -- even comp_manager/hr_admin only ever get
        their OWN row back through this endpoint."""
        self.client.force_authenticate(user=self.comp_manager.user)
        response = self.client.get("/api/v1/my-total-rewards/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["employee"], self.comp_manager.id)
        self.assertIsNone(response.data["salary"])  # comp_manager has no RemunerationRecord of their own here

    def test_no_step_up_grant_required(self):
        """Unlike PayBand/CompProposal, self-view of your own data needs
        no StepUpGrant -- self.plain_employee never obtains one anywhere
        in this test class."""
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/my-total-rewards/")
        self.assertEqual(response.status_code, 200)

    def test_statement_never_includes_any_comp_proposal(self):
        CompProposal.objects.create(
            employee=self.plain_employee, current_job_grade=self.grade, proposed_annual_salary=999999,
        )
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/my-total-rewards/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("comp_proposals", response.data)
        self.assertNotIn("proposals", response.data)
        serialized = str(response.data)
        self.assertNotIn("999999", serialized)

    def test_partial_statement_when_no_remuneration_record_exists(self):
        self.client.force_authenticate(user=self.hr_admin.user)  # has no RemunerationRecord seeded in setUp
        response = self.client.get("/api/v1/my-total-rewards/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data["salary"])
        self.assertIsNone(response.data["pay_band_position"])
