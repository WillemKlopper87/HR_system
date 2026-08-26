from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.db import IntegrityError
from django.test import TestCase
from ee_reporting.models import RemunerationRecord

from .models import Benefit, BenefitsElection, CompCycle, CompProposal, PayBand
from .services import (
    ApprovalError,
    approve_proposal,
    close_cycle,
    cycle_utilization,
    evaluate_requires_override,
    open_cycle,
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


class CompCycleModelTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

    def _cycle(self, **overrides):
        defaults = dict(
            name="FY2026 Annual Review", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("1000000"),
        )
        defaults.update(overrides)
        return CompCycle.objects.create(**defaults)

    def test_period_end_must_be_after_period_start(self):
        with self.assertRaises(IntegrityError):
            self._cycle(period_start=date(2026, 4, 1), period_end=date(2026, 4, 1))

    def test_budget_must_be_non_negative(self):
        with self.assertRaises(IntegrityError):
            self._cycle(budget_amount=Decimal("-1"))

    def test_org_wide_when_department_is_none(self):
        cycle = self._cycle(department=None)
        self.assertIsNone(cycle.department)


class CompProposalBudgetImpactTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)

    def test_bonus_impact_is_the_full_amount(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade, proposal_type=CompProposal.ProposalType.BONUS,
            bonus_amount=Decimal("20000"),
        )
        self.assertEqual(proposal.budget_impact, Decimal("20000"))

    def test_increase_impact_is_the_delta_over_baseline(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade,
            proposal_type=CompProposal.ProposalType.INCREASE,
            proposed_annual_salary=Decimal("440000"), baseline_salary_at_proposal=Decimal("400000"),
        )
        self.assertEqual(proposal.budget_impact, Decimal("40000"))

    def test_increase_impact_is_none_without_a_baseline(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade,
            proposal_type=CompProposal.ProposalType.INCREASE, proposed_annual_salary=Decimal("440000"),
        )
        self.assertIsNone(proposal.budget_impact)

    def test_amount_matching_type_constraint_rejects_a_bonus_with_a_salary_field(self):
        with self.assertRaises(IntegrityError):
            CompProposal.objects.create(
                employee=self.employee, current_job_grade=self.grade,
                proposal_type=CompProposal.ProposalType.BONUS,
                bonus_amount=Decimal("1000"), proposed_annual_salary=Decimal("400000"),
            )

    def test_amount_matching_type_constraint_rejects_an_increase_with_no_salary_field(self):
        with self.assertRaises(IntegrityError):
            CompProposal.objects.create(
                employee=self.employee, current_job_grade=self.grade,
                proposal_type=CompProposal.ProposalType.INCREASE,
            )


class ProposeWithCycleTests(TestCase):
    """propose_compensation_change's cycle-aware path (design spec §2.5):
    department scope, requiring an OPEN cycle, the baseline-required rule
    for increases, and exceeds_cycle_budget being computed at creation."""

    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.other_dept = Department.objects.create(name="Finance", code="FIN")
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        RemunerationRecord.objects.create(
            employee=self.employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=0,
        )
        PayBand.objects.create(
            job_grade=self.grade, min_salary=300000, mid_salary=400000, max_salary=500000, valid_from=date(2020, 1, 1)
        )
        self.cycle = CompCycle.objects.create(
            name="FY2026 Annual Review", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("100000"), status=CompCycle.Status.OPEN,
        )

    def test_cannot_propose_against_a_draft_cycle(self):
        draft = CompCycle.objects.create(
            name="FY2027 Draft", period_start=date(2027, 4, 1), period_end=date(2028, 3, 31),
            budget_amount=Decimal("100000"),
        )
        with self.assertRaises(ValueError):
            propose_compensation_change(
                employee=self.employee, proposed_annual_salary=420000, cycle=draft,
            )

    def test_cannot_propose_against_a_closed_cycle(self):
        self.cycle.status = CompCycle.Status.CLOSED
        self.cycle.save(update_fields=["status"])
        with self.assertRaises(ValueError):
            propose_compensation_change(employee=self.employee, proposed_annual_salary=420000, cycle=self.cycle)

    def test_department_scoped_cycle_rejects_an_employee_outside_scope(self):
        scoped_cycle = CompCycle.objects.create(
            name="Finance Only", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("100000"), department=self.other_dept, status=CompCycle.Status.OPEN,
        )
        with self.assertRaises(ValueError):
            propose_compensation_change(employee=self.employee, proposed_annual_salary=420000, cycle=scoped_cycle)

    def test_increase_without_a_remuneration_record_cannot_join_a_cycle(self):
        new_hire = _hire("E002", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        with self.assertRaises(ValueError):
            propose_compensation_change(employee=new_hire, proposed_annual_salary=420000, cycle=self.cycle)

    def test_increase_snapshots_baseline_and_computes_budget_impact(self):
        proposal = propose_compensation_change(
            employee=self.employee, proposed_annual_salary=440000, cycle=self.cycle,
        )
        self.assertEqual(proposal.baseline_salary_at_proposal, 400000)
        self.assertEqual(proposal.budget_impact, Decimal("40000"))
        self.assertFalse(proposal.exceeds_cycle_budget)

    def test_bonus_does_not_need_a_baseline(self):
        proposal = propose_compensation_change(
            employee=self.employee, proposal_type=CompProposal.ProposalType.BONUS,
            bonus_amount=50000, cycle=self.cycle,
        )
        self.assertIsNone(proposal.baseline_salary_at_proposal)
        self.assertEqual(proposal.budget_impact, Decimal("50000"))

    def test_second_proposal_that_would_blow_the_budget_is_flagged_not_blocked(self):
        propose_compensation_change(employee=self.employee, proposed_annual_salary=470000, cycle=self.cycle)  # 70k impact
        second_employee = _hire("E003", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        RemunerationRecord.objects.create(
            employee=second_employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=0,
        )
        second = propose_compensation_change(
            employee=second_employee, proposed_annual_salary=450000, cycle=self.cycle,
        )  # 50k impact, 70k + 50k = 120k > 100k budget
        self.assertTrue(second.exceeds_cycle_budget)
        # Not blocked -- still created as PROPOSED, per the "flagged, not
        # blocked" precedent requires_override already uses.
        self.assertEqual(second.status, CompProposal.Status.PROPOSED)

    def test_rejected_proposals_never_count_toward_utilization(self):
        proposal = propose_compensation_change(employee=self.employee, proposed_annual_salary=470000, cycle=self.cycle)
        reject_proposal(proposal, approver=None)
        second_employee = _hire("E003", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        RemunerationRecord.objects.create(
            employee=second_employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=0,
        )
        second = propose_compensation_change(
            employee=second_employee, proposed_annual_salary=450000, cycle=self.cycle,
        )
        self.assertFalse(second.exceeds_cycle_budget)


class CycleUtilizationTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        self.approver = _hire("E002", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        RemunerationRecord.objects.create(
            employee=self.employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=0,
        )
        # In-band, so requires_override is False and these tests exercise
        # ONLY the budget-override path, not a pay-band one too.
        PayBand.objects.create(
            job_grade=self.grade, min_salary=300000, mid_salary=400000, max_salary=500000, valid_from=date(2020, 1, 1)
        )
        self.cycle = CompCycle.objects.create(
            name="FY2026 Annual Review", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("100000"), status=CompCycle.Status.OPEN,
        )

    def test_utilization_splits_committed_and_pending(self):
        proposal = propose_compensation_change(employee=self.employee, proposed_annual_salary=440000, cycle=self.cycle)
        approve_proposal(proposal, approver=self.approver)
        summary = cycle_utilization(self.cycle)
        self.assertEqual(summary["committed_total"], Decimal("40000"))
        self.assertEqual(summary["pending_total"], Decimal("0"))
        self.assertFalse(summary["over_budget"])

    def test_approval_re_derives_exceeds_cycle_budget_fresh_not_from_creation_time(self):
        """Two increases each individually under budget but jointly over
        it: the FIRST one is created while under budget (not flagged), but
        by the time it's approved, the second has also been created and
        reserved its share -- approval must recompute fresh, not trust the
        stale creation-time flag (design spec §2.5)."""
        first = propose_compensation_change(employee=self.employee, proposed_annual_salary=440000, cycle=self.cycle)
        self.assertFalse(first.exceeds_cycle_budget)  # 40k of 100k, fine alone

        second_employee = _hire("E003", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        RemunerationRecord.objects.create(
            employee=second_employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=0,
        )
        propose_compensation_change(employee=second_employee, proposed_annual_salary=470000, cycle=self.cycle)  # +70k

        with self.assertRaises(ApprovalError):
            approve_proposal(first, approver=self.approver)  # 40k + 70k = 110k > 100k now
        self.assertTrue(first.exceeds_cycle_budget)

        approve_proposal(first, approver=self.approver, override_reason="board-approved over-run")
        self.assertEqual(first.status, CompProposal.Status.APPROVED)


class CloseCycleTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        self.cycle = CompCycle.objects.create(
            name="FY2026 Annual Review", period_start=date(2026, 4, 1), period_end=date(2027, 3, 31),
            budget_amount=Decimal("100000"), status=CompCycle.Status.OPEN,
        )

    def test_open_cycle_requires_draft_status(self):
        with self.assertRaises(ApprovalError):
            open_cycle(self.cycle)  # already OPEN in setUp

    def test_draft_cycle_can_be_opened(self):
        draft = CompCycle.objects.create(
            name="FY2027 Draft", period_start=date(2027, 4, 1), period_end=date(2028, 3, 31),
            budget_amount=Decimal("100000"),
        )
        open_cycle(draft)
        draft.refresh_from_db()
        self.assertEqual(draft.status, CompCycle.Status.OPEN)

    def test_closing_auto_rejects_still_proposed_proposals_not_silently_orphaning_them(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade, proposed_annual_salary=420000, cycle=self.cycle,
        )
        close_cycle(self.cycle, actor=self.employee)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, CompProposal.Status.REJECTED)
        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, CompCycle.Status.CLOSED)
        self.assertIsNotNone(self.cycle.closed_at)

    def test_closing_never_auto_approves_a_straggler(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade, proposed_annual_salary=420000, cycle=self.cycle,
        )
        close_cycle(self.cycle, actor=self.employee)
        proposal.refresh_from_db()
        self.assertNotEqual(proposal.status, CompProposal.Status.APPROVED)

    def test_already_closed_cycle_cannot_be_closed_again(self):
        close_cycle(self.cycle, actor=self.employee)
        with self.assertRaises(ApprovalError):
            close_cycle(self.cycle, actor=self.employee)

    def test_approved_proposals_are_left_untouched_by_close(self):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade, proposed_annual_salary=420000, cycle=self.cycle,
            status=CompProposal.Status.APPROVED,
        )
        close_cycle(self.cycle, actor=self.employee)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, CompProposal.Status.APPROVED)
