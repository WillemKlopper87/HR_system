"""ee_reporting's first read-only cross-app seam (design spec 2026-08-26
§4) -- direct unit tests, same shape as learning/performance's own
queries.py test coverage. rbac_audit.test_module_boundaries::
test_every_queries_seam_is_read_only picks this file's target up
automatically (it walks every app's queries.py, not a hardcoded list) --
no test change needed there."""
from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from .models import RemunerationRecord
from .queries import latest_remuneration_for_employee


class LatestRemunerationForEmployeeTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name="Engineering", code="ENG")
        level = OccupationalLevel.objects.get(code="TOP")
        grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
        location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
        self.employee = Employee.objects.hire(
            employee_number="E001", first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="alex@example.com", hire_date=date(2020, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )

    def test_none_when_no_record_exists(self):
        self.assertIsNone(latest_remuneration_for_employee(self.employee.id))

    def test_returns_the_most_recent_record_by_period_end(self):
        RemunerationRecord.objects.create(
            employee=self.employee, period_start=date(2024, 1, 1), period_end=date(2024, 12, 31),
            fixed_remuneration=350000, variable_remuneration=0,
        )
        latest = RemunerationRecord.objects.create(
            employee=self.employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=20000,
        )
        result = latest_remuneration_for_employee(self.employee.id)
        self.assertEqual(result["fixed_remuneration"], 400000)
        self.assertEqual(result["variable_remuneration"], 20000)
        self.assertEqual(result["total_remuneration"], 420000)
        self.assertEqual(result["period_end"], latest.period_end)

    def test_out_of_order_import_still_returns_the_latest_by_period_end(self):
        """period_start ordering would get this wrong if periods are
        imported out of chronological order -- period_end is the seam's
        deliberate choice (design spec §4)."""
        RemunerationRecord.objects.create(
            employee=self.employee, period_start=date(2025, 6, 1), period_end=date(2026, 5, 31),
            fixed_remuneration=500000, variable_remuneration=0,
        )
        RemunerationRecord.objects.create(
            employee=self.employee, period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
            fixed_remuneration=400000, variable_remuneration=0,
        )
        result = latest_remuneration_for_employee(self.employee.id)
        self.assertEqual(result["fixed_remuneration"], 500000)
