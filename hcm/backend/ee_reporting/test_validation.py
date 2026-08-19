"""H3: cell-by-cell validation of an already-generated EEA2/EEA4 snapshot
(`validate_report_data`), against the ~7 rules confirmed in
EEA-Form-Spec-Notes.md's "Consequences for the build" #7. Complements
`ValidationTests` in tests.py, which covers the pre-generation readiness
gate (`validate_report_readiness`) instead.
"""
from __future__ import annotations

from datetime import date, timedelta

from core_hr.models import EmployeeVersion
from django.test import TestCase

from . import aggregation
from .constants import BARRIER_CATEGORIES, DEMOGRAPHIC_COLUMNS
from .models import EEQuestionnaire, EEReport, EmployerConfig, RemunerationRecord
from .services import generate_report
from .tests import _hire, _seed_reference_data
from .validation import validate_report_data

PERIOD_START, PERIOD_END = date(2025, 9, 1), date(2026, 8, 31)


def _employer_config(**overrides):
    defaults = dict(
        trade_name="X", dti_registration_number="1", paye_sars_number="1", uif_reference_number="1",
        ee_reference_number="1", ceo_name="CEO", ee_senior_manager_name="EE", business_type="state_owned_enterprise",
    )
    defaults.update(overrides)
    return EmployerConfig.objects.create(**defaults)


def _full_barriers():
    return {key: {"barriers": False, "aa_measures": False} for key, _label in BARRIER_CATEGORIES}


def _clean_matrix():
    """A hand-built, internally-consistent 10-column matrix — same shape
    `aggregation.empty_matrix()` produces, with one employee in TOP."""
    matrix = aggregation.empty_matrix()
    matrix["TOP"]["african_male"] = 1
    matrix["total_permanent"]["african_male"] = 1
    matrix["grand_total"]["african_male"] = 1
    return matrix


def _eea2_report(**data_overrides):
    data = {
        "employer": {}, "questionnaire": {"barriers": _full_barriers()},
        "workforce_profile": _clean_matrix(), "disability_workforce": _clean_matrix(),
        "recruitment": _clean_matrix(), "promotion": _clean_matrix(), "termination": _clean_matrix(),
        "skills_development": _clean_matrix(),
    }
    data.update(data_overrides)
    return EEReport.objects.create(
        form_type=EEReport.FormType.EEA2, report_year=2026, version=1,
        period_start=PERIOD_START, period_end=PERIOD_END, data=data,
    )


def _eea4_report(**data_overrides):
    data = {
        "employer": {}, "questionnaire": {},
        "number_of_employees": _clean_matrix(), "total_remuneration": _clean_matrix(),
        "highest_paid": {}, "lowest_paid_lowest_level": {},
        "median_and_gap": {
            "median_remuneration": 300000, "top_5_pct": {"total": 300000, "range_low": 300000, "range_high": 300000},
            "bottom_5_pct": {"total": 300000, "range_low": 300000, "range_high": 300000},
        },
    }
    data.update(data_overrides)
    return EEReport.objects.create(
        form_type=EEReport.FormType.EEA4, report_year=2026, version=1,
        period_start=PERIOD_START, period_end=PERIOD_END, data=data,
    )


class MatrixCompletenessTests(TestCase):
    def test_clean_report_has_no_completeness_issues(self):
        report = _eea2_report()
        self.assertEqual(validate_report_data(report), [])

    def test_missing_cell_is_reported(self):
        matrix = _clean_matrix()
        del matrix["SENIOR"]["african_male"]
        report = _eea2_report(workforce_profile=matrix)
        issues = validate_report_data(report)
        self.assertTrue(any("workforce_profile[SENIOR][african_male]" in i and "missing" in i for i in issues))

    def test_null_cell_is_reported(self):
        matrix = _clean_matrix()
        matrix["SENIOR"]["african_male"] = None
        report = _eea2_report(workforce_profile=matrix)
        issues = validate_report_data(report)
        self.assertTrue(any("workforce_profile[SENIOR][african_male]" in i and "missing" in i for i in issues))

    def test_negative_cell_is_reported(self):
        matrix = _clean_matrix()
        matrix["SENIOR"]["african_male"] = -1
        report = _eea2_report(workforce_profile=matrix)
        issues = validate_report_data(report)
        self.assertTrue(any("workforce_profile[SENIOR][african_male]" in i for i in issues))

    def test_missing_section_is_reported(self):
        report = _eea2_report()
        del report.data["termination"]
        report.save(update_fields=["data"])
        issues = validate_report_data(report)
        self.assertTrue(any("termination" in i and "missing from the generated data" in i for i in issues))


class MatrixArithmeticTests(TestCase):
    def test_total_permanent_not_matching_level_sum_is_reported(self):
        matrix = _clean_matrix()
        matrix["total_permanent"]["african_male"] = 5  # actual level rows still sum to 1
        report = _eea2_report(workforce_profile=matrix)
        issues = validate_report_data(report)
        self.assertTrue(any("total_permanent][african_male] = 5" in i for i in issues))

    def test_grand_total_not_matching_permanent_plus_temporary_is_reported(self):
        matrix = _clean_matrix()
        matrix["grand_total"]["african_male"] = 99
        report = _eea2_report(workforce_profile=matrix)
        issues = validate_report_data(report)
        self.assertTrue(any("grand_total][african_male] = 99" in i for i in issues))


class IntegerRemunerationTests(TestCase):
    def test_clean_eea4_has_no_remuneration_issues(self):
        report = _eea4_report()
        self.assertEqual(validate_report_data(report), [])

    def test_float_in_total_remuneration_matrix_is_reported(self):
        matrix = _clean_matrix()
        matrix["TOP"]["african_male"] = 300000.5
        report = _eea4_report(total_remuneration=matrix)
        issues = validate_report_data(report)
        self.assertTrue(any("total_remuneration[TOP][african_male]" in i for i in issues))

    def test_float_median_remuneration_is_reported(self):
        report = _eea4_report(median_and_gap={
            "median_remuneration": 300000.5,
            "top_5_pct": {"total": 0, "range_low": None, "range_high": None},
            "bottom_5_pct": {"total": 0, "range_low": None, "range_high": None},
        })
        issues = validate_report_data(report)
        self.assertTrue(any("median_and_gap[median_remuneration]" in i for i in issues))

    def test_float_in_highest_paid_is_reported(self):
        report = _eea4_report(highest_paid={"TOP": {"african_male": {"fixed": 100.5, "variable": 0, "total": 100.5}}})
        issues = validate_report_data(report)
        self.assertTrue(any("highest_paid[TOP][african_male][fixed]" in i for i in issues))

    def test_median_aggregation_never_produces_a_float(self):
        """Regression: an even-count median used to average two ints with
        `/`, landing on a X.5 -- fixed to round back to a whole Rand."""
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        for i, amount in enumerate([100000, 100001]):
            emp = _hire(f"E{i:03d}", dept=dept, level=level, grade=grade, location=location)
            RemunerationRecord.objects.create(
                employee=emp, period_start=PERIOD_START, period_end=PERIOD_END, fixed_remuneration=amount,
            )
        stats = aggregation.median_and_gap_stats(PERIOD_START, PERIOD_END)
        self.assertIsInstance(stats["median_remuneration"], int)
        # (100000 + 100001) / 2 == 100000.5 -> round() to the nearest whole
        # Rand; Python's round() is banker's rounding, so .5 goes to the
        # nearest *even* integer (100000), not always up.
        self.assertEqual(stats["median_remuneration"], 100000)


class FrozenCrossFormHeadcountTests(TestCase):
    def test_matching_headcounts_report_no_issue(self):
        _eea2_report()
        eea4 = _eea4_report(number_of_employees=_clean_matrix())
        self.assertEqual(validate_report_data(eea4), [])

    def test_mismatched_headcounts_are_reported(self):
        _eea2_report()  # grand_total.african_male == 1
        mismatched = aggregation.empty_matrix()
        mismatched["TOP"]["african_male"] = 2
        mismatched["total_permanent"]["african_male"] = 2
        mismatched["grand_total"]["african_male"] = 2
        eea4 = _eea4_report(number_of_employees=mismatched)
        issues = validate_report_data(eea4)
        self.assertTrue(any("headcount doesn't match" in i and "african_male" in i for i in issues))

    def test_no_current_eea2_is_silently_skipped_not_double_reported(self):
        """validate_report_readiness already blocks generation without a
        current EEA2 -- this check only runs on an EEA4 that exists
        despite that (e.g. the matching EEA2 was later deleted/re-superseded)."""
        eea4 = _eea4_report()
        self.assertEqual(validate_report_data(eea4), [])


class BarrierGridCompletenessTests(TestCase):
    def test_full_24_category_grid_has_no_issues(self):
        report = _eea2_report()
        self.assertEqual(validate_report_data(report), [])

    def test_empty_barriers_grid_flags_every_category(self):
        report = _eea2_report(questionnaire={"barriers": {}})
        issues = validate_report_data(report)
        barrier_issues = [i for i in issues if "Barriers & AA measures" in i]
        self.assertEqual(len(barrier_issues), len(BARRIER_CATEGORIES))

    def test_category_missing_one_of_the_two_answers_is_reported(self):
        barriers = _full_barriers()
        del barriers["recruitment"]["aa_measures"]
        report = _eea2_report(questionnaire={"barriers": barriers})
        issues = validate_report_data(report)
        self.assertTrue(any("Recruitment" in i and "aa_measures" in i for i in issues))


class TemporaryClassificationTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.junior, self.grade, self.junior_grade, self.location = _seed_reference_data()

    def test_temporary_employee_open_over_90_days_is_flagged(self):
        # _hire()'s hardcoded hire_date (2020-01-01) is already years before
        # PERIOD_END, so a TEMPORARY-status hire is an immediate violation.
        emp = _hire(
            "E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location,
            employment_status=EmployeeVersion.EmploymentStatus.TEMPORARY,
        )
        report = _eea2_report()
        issues = validate_report_data(report)
        self.assertTrue(any(emp.employee_number in i and "Temporary" in i for i in issues))

    def test_temporary_employee_within_90_days_is_not_flagged(self):
        emp = _hire(
            "E002", dept=self.dept, level=self.level, grade=self.grade, location=self.location,
            employment_status=EmployeeVersion.EmploymentStatus.TEMPORARY,
        )
        EmployeeVersion.objects.filter(pk=emp.current_version.pk).update(valid_from=PERIOD_END - timedelta(days=30))
        report = _eea2_report()
        issues = validate_report_data(report)
        self.assertFalse(any(emp.employee_number in i for i in issues))

    def test_permanent_employee_is_never_flagged(self):
        _hire("E003", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        report = _eea2_report()
        self.assertEqual(validate_report_data(report), [])


class GeneratedReportIntegrationTests(TestCase):
    """A real, full-pipeline generate_report() call (not a hand-built
    fixture) should come back clean -- proves the checks agree with what
    aggregation.py actually produces, not just with hand-crafted data."""

    def test_a_freshly_generated_clean_eea2_has_no_issues(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        _hire("E001", dept=dept, level=level, grade=grade, location=location)
        _employer_config()
        EEQuestionnaire.objects.create(report_year=2026, barriers=_full_barriers())
        report = generate_report(form_type="eea2", report_year=2026, period_start=PERIOD_START, period_end=PERIOD_END)
        self.assertEqual(validate_report_data(report), [])

    def test_a_freshly_generated_clean_eea4_has_no_issues(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        RemunerationRecord.objects.create(
            employee=emp, period_start=PERIOD_START, period_end=PERIOD_END, fixed_remuneration=300000,
        )
        _employer_config()
        EEQuestionnaire.objects.create(report_year=2026, barriers=_full_barriers())
        generate_report(form_type="eea2", report_year=2026, period_start=PERIOD_START, period_end=PERIOD_END)
        eea4 = generate_report(form_type="eea4", report_year=2026, period_start=PERIOD_START, period_end=PERIOD_END)
        self.assertEqual(validate_report_data(eea4), [])
