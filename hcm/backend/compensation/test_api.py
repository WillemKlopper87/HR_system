from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Benefit, BenefitsElection, CompProposal, PayBand

User = get_user_model()


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


class ModuleWidePermissionTests(CompensationApiTestCase):
    """Sprint 10 acceptance criterion: 'Pay-data visibility restricted to
    comp manager/HR admin roles only (strict RBAC)' — applies to every
    endpoint in the module, including the benefits catalog, not just
    individual pay figures."""

    def test_line_manager_cannot_view_pay_bands(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get("/api/v1/pay-bands/")
        self.assertEqual(response.status_code, 403)

    def test_plain_employee_cannot_view_comp_proposals(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/comp-proposals/")
        self.assertEqual(response.status_code, 403)

    def test_plain_employee_cannot_view_benefits_catalog(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/benefits/")
        self.assertEqual(response.status_code, 403)

    def test_plain_employee_cannot_view_benefits_elections(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/benefits-elections/")
        self.assertEqual(response.status_code, 403)

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
