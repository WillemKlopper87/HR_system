"""H3 org-wide data-quality sweep: this app's own overdue-stage check,
registered from `PerformanceConfig.ready()` (see performance/data_quality.py).
Reuses reminders.py's own "who is outstanding for the open phase" logic, so
these tests pin the "and it's overdue" half specifically.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from core_hr.data_quality import run_data_quality_checks
from core_hr.models import DataQualityException, Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .data_quality import overdue_agreement_handler
from .models import AgreementTemplate, PerformancePeriod, PeriodPhase, TemplateElement, TemplateSection
from .services import create_agreement, publish_template

LEVELS = {str(i): f"level {i}" for i in range(1, 6)}


class OverdueAgreementHandlerTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name="Operations", code="OPS")
        level = OccupationalLevel.objects.get(code="TOP")
        grade = JobGrade.objects.create(name="G1", code="G1", occupational_level=level)
        location = Location.objects.create(name="HO", code="HO", province=Location.Province.GAUTENG)
        self.employee = Employee.objects.hire(
            employee_number="E0050", first_name="Overdue", last_name="Case", date_of_birth=date(1990, 1, 1),
            work_email="overdue.case@example.com", hire_date=date(2020, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )
        self.template = self._template()

    def _template(self):
        template = AgreementTemplate.objects.create(name="Scorecard", version=1)
        section = TemplateSection.objects.create(template=template, title="Objective", order=0)
        TemplateElement.objects.create(
            template=template, section=section, kpi_title="KPI 1", default_weight=Decimal("1.0"),
            level_descriptors=dict(LEVELS),
        )
        return publish_template(template)

    def _period(self, *, due_on, status=PerformancePeriod.Status.CONTRACTING):
        period = PerformancePeriod.objects.create(
            name="2026/27", start_date=date(2026, 4, 1), end_date=date(2027, 3, 31), status=status,
        )
        PeriodPhase.objects.create(
            period=period, stage=PeriodPhase.Stage.CONTRACTING, opens_on=date(2026, 4, 1), due_on=due_on,
        )
        return period

    def test_agreement_past_due_on_open_phase_is_flagged(self):
        period = self._period(due_on=date.today() - timedelta(days=5))
        create_agreement(period=period, employee=self.employee, template=self.template)

        flagged = list(overdue_agreement_handler())
        self.assertEqual([e for e, _ in flagged], [self.employee])

    def test_agreement_not_yet_due_is_not_flagged(self):
        period = self._period(due_on=date.today() + timedelta(days=5))
        create_agreement(period=period, employee=self.employee, template=self.template)

        self.assertEqual(list(overdue_agreement_handler()), [])

    def test_period_with_no_open_phase_is_skipped(self):
        period = self._period(due_on=date.today() - timedelta(days=5), status=PerformancePeriod.Status.CLOSED)
        create_agreement(period=period, employee=self.employee, template=self.template)

        self.assertEqual(list(overdue_agreement_handler()), [])

    def test_wired_into_the_org_wide_sweep(self):
        period = self._period(due_on=date.today() - timedelta(days=5))
        create_agreement(period=period, employee=self.employee, template=self.template)

        run_data_quality_checks()

        self.assertTrue(
            DataQualityException.objects.filter(
                employee=self.employee,
                exception_type=DataQualityException.ExceptionType.PERFORMANCE_OVERDUE,
                resolved_at__isnull=True,
            ).exists()
        )
