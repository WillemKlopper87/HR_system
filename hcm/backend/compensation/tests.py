from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.db import IntegrityError
from django.test import TestCase

from .models import Benefit, BenefitsElection, PayBand
from .services import (
    ApprovalError,
    approve_proposal,
    evaluate_requires_override,
    propose_compensation_change,
    reject_proposal,
)


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


def _hire(employee_number, *, dept, level, grade, location, **overrides):
    defaults = dict(
        first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
        work_email=f"{employee_number.lower()}@example.com", hire_date=date(2020, 1, 1),
        department=dept, occupational_level=level, job_grade=grade, location=location,
    )
    defaults.update(overrides)
    return Employee.objects.hire(employee_number=employee_number, **defaults)


class PayBandTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def test_contains_is_inclusive_of_bounds(self):
        band = PayBand.objects.create(
            job_grade=self.grade, min_salary=300000, mid_salary=400000, max_salary=500000, valid_from=date(2024, 1, 1)
        )
        self.assertTrue(band.contains(300000))
        self.assertTrue(band.contains(500000))
        self.assertTrue(band.contains(400000))
        self.assertFalse(band.contains(299999))
        self.assertFalse(band.contains(500001))

    def test_min_mid_max_ordering_constraint_is_enforced_at_db_level(self):
        with self.assertRaises(IntegrityError):
            PayBand.objects.create(
                job_grade=self.grade, min_salary=500000, mid_salary=300000, max_salary=400000,
                valid_from=date(2024, 1, 1),
            )

    def test_current_returns_only_the_band_valid_as_of_today(self):
        PayBand.objects.create(
            job_grade=self.grade, min_salary=200000, mid_salary=250000, max_salary=300000,
            valid_from=date(2000, 1, 1), valid_to=date(2020, 1, 1),
        )
        current = PayBand.objects.create(
            job_grade=self.grade, min_salary=300000, mid_salary=400000, max_salary=500000, valid_from=date(2020, 1, 2)
        )
        result = PayBand.objects.filter(job_grade=self.grade).current().first()
        self.assertEqual(result, current)


class EvaluateRequiresOverrideTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        PayBand.objects.create(
            job_grade=self.grade, min_salary=300000, mid_salary=400000, max_salary=500000, valid_from=date(2020, 1, 1)
        )

    def test_in_band_salary_does_not_require_override(self):
        self.assertFalse(evaluate_requires_override(self.employee, 450000))

    def test_out_of_band_salary_requires_override(self):
        self.assertTrue(evaluate_requires_override(self.employee, 999999))

    def test_no_pay_band_for_grade_requires_override(self):
        other_grade = JobGrade.objects.create(name="Grade 2", code="G2", occupational_level=self.level)
        employee = _hire("E002", dept=self.dept, level=self.level, grade=other_grade, location=self.location)
        self.assertTrue(evaluate_requires_override(employee, 350000))

    def test_employee_with_no_job_grade_requires_override(self):
        employee = _hire("E003", dept=self.dept, level=self.level, grade=None, location=self.location)
        self.assertTrue(evaluate_requires_override(employee, 350000))


class ProposeApproveRejectWorkflowTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        self.proposer = _hire("E002", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        self.approver = _hire("E003", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        PayBand.objects.create(
            job_grade=self.grade, min_salary=300000, mid_salary=400000, max_salary=500000, valid_from=date(2020, 1, 1)
        )

    def test_propose_snapshots_current_job_grade_and_flags_override(self):
        proposal = propose_compensation_change(
            employee=self.employee, proposed_annual_salary=999999, proposed_by=self.proposer
        )
        self.assertEqual(proposal.current_job_grade, self.grade)
        self.assertTrue(proposal.requires_override)
        self.assertEqual(proposal.status, "proposed")

    def test_proposer_cannot_approve_own_proposal(self):
        proposal = propose_compensation_change(
            employee=self.employee, proposed_annual_salary=350000, proposed_by=self.proposer
        )
        with self.assertRaises(ApprovalError):
            approve_proposal(proposal, approver=self.proposer)

    def test_out_of_band_approval_requires_override_reason(self):
        proposal = propose_compensation_change(
            employee=self.employee, proposed_annual_salary=999999, proposed_by=self.proposer
        )
        with self.assertRaises(ApprovalError):
            approve_proposal(proposal, approver=self.approver)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "proposed")

        approve_proposal(proposal, approver=self.approver, override_reason="market adjustment")
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "approved")
        self.assertEqual(proposal.override_reason, "market adjustment")
        self.assertEqual(proposal.approved_by, self.approver)

    def test_in_band_approval_does_not_require_override_reason(self):
        proposal = propose_compensation_change(
            employee=self.employee, proposed_annual_salary=350000, proposed_by=self.proposer
        )
        approve_proposal(proposal, approver=self.approver)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "approved")

    def test_cannot_approve_or_reject_a_non_proposed_proposal(self):
        proposal = propose_compensation_change(
            employee=self.employee, proposed_annual_salary=350000, proposed_by=self.proposer
        )
        approve_proposal(proposal, approver=self.approver)
        with self.assertRaises(ApprovalError):
            approve_proposal(proposal, approver=self.approver)
        with self.assertRaises(ApprovalError):
            reject_proposal(proposal, approver=self.approver)

    def test_reject_sets_status_and_approver(self):
        proposal = propose_compensation_change(
            employee=self.employee, proposed_annual_salary=350000, proposed_by=self.proposer
        )
        reject_proposal(proposal, approver=self.approver)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, "rejected")
        self.assertEqual(proposal.approved_by, self.approver)

    def test_propose_for_employee_with_no_job_grade_is_rejected(self):
        employee = _hire("E004", dept=self.dept, level=self.level, grade=None, location=self.location)
        with self.assertRaises(ValueError):
            propose_compensation_change(employee=employee, proposed_annual_salary=350000)


class BenefitsElectionTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        self.benefit = Benefit.objects.create(name="Medical Aid", category=Benefit.Category.MEDICAL)

    def test_one_election_per_employee_per_benefit_is_enforced(self):
        BenefitsElection.objects.create(employee=self.employee, benefit=self.benefit, status=BenefitsElection.Status.ENROLLED)
        with self.assertRaises(IntegrityError):
            BenefitsElection.objects.create(employee=self.employee, benefit=self.benefit, status=BenefitsElection.Status.WAIVED)
