"""performance/queries.py -- the read-only seam succession's candidate
cards use for performance context (C6, docs/superpowers/specs/2026-08-25-
succession-talent-pools-design.md §2.7). First caller of this seam --
performance had none before."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .models import AgreementTemplate, PerformanceAgreement, PerformancePeriod
from .queries import latest_final_score


class LatestFinalScoreQueryTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name="Finance", code="FIN")
        level = OccupationalLevel.objects.get(code="TOP")
        grade = JobGrade.objects.create(name="G1", code="G1", occupational_level=level)
        location = Location.objects.create(name="HO", code="HO", province=Location.Province.GAUTENG)
        self.employee = Employee.objects.hire(
            employee_number="E300", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="e300@example.com", hire_date=date(2020, 1, 1), department=dept, occupational_level=level,
            job_grade=grade, location=location,
        )
        self.template = AgreementTemplate.objects.create(name="Scorecard", version=1)

    def _period(self, name, start_date):
        return PerformancePeriod.objects.create(name=name, start_date=start_date, end_date=date(start_date.year + 1, 3, 31))

    def test_no_scored_agreement_returns_none(self):
        self.assertIsNone(latest_final_score(self.employee.id))

    def test_unscored_agreement_is_ignored(self):
        period = self._period("2025/26", date(2025, 4, 1))
        PerformanceAgreement.objects.create(
            period=period, employee=self.employee, template=self.template, template_version=1,
        )
        self.assertIsNone(latest_final_score(self.employee.id))

    def test_returns_most_recent_scored_period(self):
        older = self._period("2024/25", date(2024, 4, 1))
        newer = self._period("2025/26", date(2025, 4, 1))
        PerformanceAgreement.objects.create(
            period=older, employee=self.employee, template=self.template, template_version=1,
            final_score=Decimal("3.00"),
        )
        PerformanceAgreement.objects.create(
            period=newer, employee=self.employee, template=self.template, template_version=1,
            final_score=Decimal("4.50"), hr_attention=False,
        )
        result = latest_final_score(self.employee.id)
        self.assertEqual(result["final_score"], Decimal("4.50"))
        self.assertEqual(result["period_name"], "2025/26")
        self.assertFalse(result["hr_attention"])
