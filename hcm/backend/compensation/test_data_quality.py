"""H3 org-wide data-quality sweep: this app's own stale-proposal check,
registered from `CompensationConfig.ready()` (see compensation/data_quality.py).
"""
from __future__ import annotations

from datetime import date, timedelta

from core_hr.data_quality import run_data_quality_checks
from core_hr.models import DataQualityException, Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase
from django.utils import timezone

from .data_quality import STALE_AFTER_DAYS, stale_proposal_handler
from .models import CompProposal


class StaleProposalHandlerTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name="Engineering", code="ENG")
        level = OccupationalLevel.objects.get(code="TOP")
        self.grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
        location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
        self.employee = Employee.objects.hire(
            employee_number="E0060", first_name="Stale", last_name="Case", date_of_birth=date(1990, 1, 1),
            work_email="stale.case@example.com", hire_date=date(2020, 1, 1), department=dept,
            occupational_level=level, job_grade=self.grade, location=location,
        )

    def _proposal(self, *, age_days, status=CompProposal.Status.PROPOSED):
        proposal = CompProposal.objects.create(
            employee=self.employee, current_job_grade=self.grade, proposed_annual_salary=350000, status=status,
        )
        CompProposal.objects.filter(pk=proposal.pk).update(created_at=timezone.now() - timedelta(days=age_days))
        return proposal

    def test_proposal_older_than_threshold_is_flagged(self):
        self._proposal(age_days=STALE_AFTER_DAYS + 1)
        flagged = list(stale_proposal_handler())
        self.assertEqual([e for e, _ in flagged], [self.employee])

    def test_proposal_within_threshold_is_not_flagged(self):
        self._proposal(age_days=STALE_AFTER_DAYS - 1)
        self.assertEqual(list(stale_proposal_handler()), [])

    def test_approved_proposal_is_not_flagged_regardless_of_age(self):
        self._proposal(age_days=STALE_AFTER_DAYS + 30, status=CompProposal.Status.APPROVED)
        self.assertEqual(list(stale_proposal_handler()), [])

    def test_wired_into_the_org_wide_sweep(self):
        self._proposal(age_days=STALE_AFTER_DAYS + 1)
        run_data_quality_checks()
        self.assertTrue(
            DataQualityException.objects.filter(
                employee=self.employee,
                exception_type=DataQualityException.ExceptionType.COMP_PROPOSAL_STALE,
                resolved_at__isnull=True,
            ).exists()
        )
