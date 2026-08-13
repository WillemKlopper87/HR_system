from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, EmployeeVersion, EmploymentEvent, JobGrade, Location, OccupationalLevel
from django.db import IntegrityError
from django.test import TestCase
from learning.models import TrainingRecord

from . import aggregation, export
from .constants import BARRIER_CATEGORIES, CONSULTATION_STAKEHOLDERS, DIFFERENTIAL_REASONS, JUSTIFIABLE_REASONS
from .models import EEQuestionnaire, EEReport, EmployerConfig, RemunerationRecord
from .services import (
    ApprovalError,
    RemunerationImportError,
    ReportNotReadyError,
    ee_manager_approve,
    generate_report,
    import_remuneration_csv,
    sign_off,
    submit_for_review,
)
from .validation import validate_report_readiness


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    junior = OccupationalLevel.objects.get(code="UNSKILLED")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    junior_grade = JobGrade.objects.create(name="Grade J", code="GJ", occupational_level=junior)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, junior, grade, junior_grade, location


def _hire(number, *, dept, level, grade, location, race="african", gender="male", citizenship=None, employment_status=None):
    return Employee.objects.hire(
        employee_number=number, first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
        work_email=f"{number.lower()}@example.com", hire_date=date(2020, 1, 1),
        department=dept, occupational_level=level, job_grade=grade, location=location,
        race=race, gender=gender,
        citizenship_status=citizenship or EmployeeVersion.CitizenshipStatus.SA_CITIZEN_BIRTH_DESCENT,
        employment_status=employment_status or EmployeeVersion.EmploymentStatus.PERMANENT,
    )


class ConstantsTests(TestCase):
    def test_barrier_categories_count_matches_form_spec(self):
        self.assertEqual(len(BARRIER_CATEGORIES), 24)

    def test_justifiable_reasons_count_matches_form_spec(self):
        self.assertEqual(len(JUSTIFIABLE_REASONS), 7)

    def test_differential_reasons_count_matches_form_spec(self):
        self.assertEqual(len(DIFFERENTIAL_REASONS), 8)

    def test_consultation_stakeholders_count_matches_form_spec(self):
        self.assertEqual(len(CONSULTATION_STAKEHOLDERS), 3)


class DemographicColumnTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.junior, self.grade, self.junior_grade, self.location = _seed_reference_data()

    def test_sa_citizen_maps_to_race_gender_column(self):
        emp = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location, race="coloured", gender="female")
        self.assertEqual(aggregation.demographic_column(emp.current_version), "coloured_female")

    def test_foreign_national_maps_to_fn_column_regardless_of_race(self):
        emp = _hire(
            "E002", dept=self.dept, level=self.level, grade=self.grade, location=self.location,
            race="white", gender="male", citizenship=EmployeeVersion.CitizenshipStatus.FOREIGN_NATIONAL,
        )
        self.assertEqual(aggregation.demographic_column(emp.current_version), "foreign_national_male")

    def test_not_disclosed_race_maps_to_none(self):
        emp = _hire("E003", dept=self.dept, level=self.level, grade=self.grade, location=self.location, race="not_disclosed")
        self.assertIsNone(aggregation.demographic_column(emp.current_version))

    def test_not_disclosed_gender_maps_to_none(self):
        emp = _hire("E004", dept=self.dept, level=self.level, grade=self.grade, location=self.location, gender="not_disclosed")
        self.assertIsNone(aggregation.demographic_column(emp.current_version))


class WorkforceProfileMatrixTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.junior, self.grade, self.junior_grade, self.location = _seed_reference_data()

    def test_permanent_employee_counted_in_own_level(self):
        _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location, race="african", gender="male")
        matrix = aggregation.workforce_profile_matrix(date.today())
        self.assertEqual(matrix["TOP"]["african_male"], 1)
        self.assertEqual(matrix["total_permanent"]["african_male"], 1)
        self.assertEqual(matrix["grand_total"]["african_male"], 1)

    def test_temporary_employee_counted_separately_not_in_level_row(self):
        _hire(
            "E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location,
            employment_status=EmployeeVersion.EmploymentStatus.TEMPORARY,
        )
        matrix = aggregation.workforce_profile_matrix(date.today())
        self.assertEqual(matrix["TOP"]["african_male"], 0)
        self.assertEqual(matrix["temporary_employees"]["african_male"], 1)
        self.assertEqual(matrix["grand_total"]["african_male"], 1)

    def test_grand_total_is_sum_of_permanent_and_temporary(self):
        _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        _hire(
            "E002", dept=self.dept, level=self.level, grade=self.grade, location=self.location,
            employment_status=EmployeeVersion.EmploymentStatus.TEMPORARY,
        )
        matrix = aggregation.workforce_profile_matrix(date.today())
        self.assertEqual(matrix["grand_total"]["african_male"], 2)


class DisabilityMatrixTests(TestCase):
    def test_only_disabled_employees_counted(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        version = emp.current_version
        version.disability_status = EmployeeVersion.DisabilityStatus.YES
        version.save(update_fields=["disability_status"])
        _hire("E002", dept=dept, level=level, grade=grade, location=location)

        matrix = aggregation.disability_workforce_matrix(date.today())
        self.assertEqual(matrix["TOP"]["african_male"], 1)
        self.assertEqual(aggregation.workforce_profile_matrix(date.today())["TOP"]["african_male"], 2)


class MovementMatrixTests(TestCase):
    def test_hire_event_within_period_is_counted(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        EmploymentEvent.objects.create(
            employee=emp, event_type=EmploymentEvent.EventType.HIRE, effective_date=date(2026, 3, 1),
            to_version=emp.current_version,
        )
        matrix = aggregation.movement_matrix("hire", date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(matrix["TOP"]["african_male"], 1)

    def test_event_outside_period_is_not_counted(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        EmploymentEvent.objects.create(
            employee=emp, event_type=EmploymentEvent.EventType.HIRE, effective_date=date(2020, 3, 1),
            to_version=emp.current_version,
        )
        matrix = aggregation.movement_matrix("hire", date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(matrix["TOP"]["african_male"], 0)


class SkillsDevelopmentMatrixTests(TestCase):
    def test_completed_training_in_period_counts_employee(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        TrainingRecord.objects.create(
            employee=emp, title="Leadership 101", status=TrainingRecord.Status.COMPLETED, completion_date=date(2026, 5, 1),
        )
        matrix = aggregation.skills_development_matrix(date(2026, 1, 1), date(2026, 12, 31), date(2026, 12, 31))
        self.assertEqual(matrix["TOP"]["african_male"], 1)

    def test_in_progress_training_does_not_count(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        TrainingRecord.objects.create(employee=emp, title="Leadership 101", status=TrainingRecord.Status.IN_PROGRESS)
        matrix = aggregation.skills_development_matrix(date(2026, 1, 1), date(2026, 12, 31), date(2026, 12, 31))
        self.assertEqual(matrix["TOP"]["african_male"], 0)


class RemunerationAggregationTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.junior, self.grade, self.junior_grade, self.location = _seed_reference_data()
        self.period_start, self.period_end = date(2025, 9, 1), date(2026, 8, 31)

    def test_headcount_and_remuneration_matrix(self):
        emp = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        RemunerationRecord.objects.create(
            employee=emp, period_start=self.period_start, period_end=self.period_end,
            fixed_remuneration=300000, variable_remuneration=50000,
        )
        result = aggregation.headcount_and_remuneration_matrix(self.period_start, self.period_end, self.period_end)
        self.assertEqual(result["number_of_employees"]["TOP"]["african_male"], 1)
        self.assertEqual(result["total_remuneration"]["TOP"]["african_male"], 350000)

    def test_highest_and_lowest_paid_tie_break_prefers_higher_variable(self):
        emp_a = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        emp_b = _hire("E002", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        RemunerationRecord.objects.create(
            employee=emp_a, period_start=self.period_start, period_end=self.period_end,
            fixed_remuneration=350000, variable_remuneration=50000,
        )
        RemunerationRecord.objects.create(
            employee=emp_b, period_start=self.period_start, period_end=self.period_end,
            fixed_remuneration=300000, variable_remuneration=100000,
        )
        result = aggregation.highest_and_lowest_paid_by_level(self.period_start, self.period_end, self.period_end)
        # both total 400000; higher-variable (emp_b, 100000) should win for "highest"
        self.assertEqual(result["highest_paid"]["TOP"]["african_male"]["variable"], 100000)

    def test_lowest_paid_only_reported_for_lowest_level(self):
        _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        emp = Employee.objects.get(employee_number="E001")
        RemunerationRecord.objects.create(
            employee=emp, period_start=self.period_start, period_end=self.period_end,
            fixed_remuneration=300000, variable_remuneration=0,
        )
        result = aggregation.highest_and_lowest_paid_by_level(self.period_start, self.period_end, self.period_end)
        self.assertEqual(result["lowest_paid_lowest_level"], {})  # employee is TOP level, not UNSKILLED

    def test_median_and_gap_stats_odd_count(self):
        for i, amount in enumerate([100000, 200000, 300000]):
            emp = _hire(f"E00{i}", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
            RemunerationRecord.objects.create(
                employee=emp, period_start=self.period_start, period_end=self.period_end,
                fixed_remuneration=amount, variable_remuneration=0,
            )
        stats = aggregation.median_and_gap_stats(self.period_start, self.period_end)
        self.assertEqual(stats["median_remuneration"], 200000)
        self.assertEqual(stats["vertical_gap_multiple"], 3.0)

    def test_median_and_gap_stats_no_records(self):
        stats = aggregation.median_and_gap_stats(self.period_start, self.period_end)
        self.assertEqual(stats["employee_count"], 0)
        self.assertIsNone(stats["median_remuneration"])


class RemunerationRecordModelTests(TestCase):
    def test_one_record_per_employee_per_period(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        RemunerationRecord.objects.create(
            employee=emp, period_start=date(2025, 9, 1), period_end=date(2026, 8, 31), fixed_remuneration=300000,
        )
        with self.assertRaises(IntegrityError):
            RemunerationRecord.objects.create(
                employee=emp, period_start=date(2025, 9, 1), period_end=date(2026, 8, 31), fixed_remuneration=400000,
            )

    def test_total_remuneration_property(self):
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        record = RemunerationRecord.objects.create(
            employee=emp, period_start=date(2025, 9, 1), period_end=date(2026, 8, 31),
            fixed_remuneration=300000, variable_remuneration=50000,
        )
        self.assertEqual(record.total_remuneration, 350000)


class RemunerationCsvImportTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.junior, self.grade, self.junior_grade, self.location = _seed_reference_data()
        self.emp = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)

    def test_valid_csv_creates_a_record(self):
        csv_text = "employee_number,period_start,period_end,fixed_remuneration,variable_remuneration\nE001,2025-09-01,2026-08-31,300000,50000"
        result = import_remuneration_csv(csv_text)
        self.assertEqual(result, {"created": 1, "updated": 0, "errors": []})
        self.assertTrue(RemunerationRecord.objects.filter(employee=self.emp).exists())

    def test_missing_columns_raises(self):
        with self.assertRaises(RemunerationImportError):
            import_remuneration_csv("a,b\n1,2")

    def test_unknown_employee_number_is_reported_as_a_row_error_not_a_crash(self):
        csv_text = "employee_number,period_start,period_end,fixed_remuneration,variable_remuneration\nNOPE,2025-09-01,2026-08-31,300000,50000"
        result = import_remuneration_csv(csv_text)
        self.assertEqual(result["created"], 0)
        self.assertEqual(len(result["errors"]), 1)

    def test_reimporting_same_employee_period_updates_in_place(self):
        csv_text = "employee_number,period_start,period_end,fixed_remuneration,variable_remuneration\nE001,2025-09-01,2026-08-31,300000,50000"
        import_remuneration_csv(csv_text)
        csv_text2 = "employee_number,period_start,period_end,fixed_remuneration,variable_remuneration\nE001,2025-09-01,2026-08-31,320000,60000"
        result = import_remuneration_csv(csv_text2)
        self.assertEqual(result, {"created": 0, "updated": 1, "errors": []})
        record = RemunerationRecord.objects.get(employee=self.emp)
        self.assertEqual(record.fixed_remuneration, 320000)


class ReportGenerationServiceTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.junior, self.grade, self.junior_grade, self.location = _seed_reference_data()
        _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        self.period_start, self.period_end = date(2025, 9, 1), date(2026, 8, 31)

    def test_generate_blocked_without_employer_config(self):
        with self.assertRaises(ReportNotReadyError):
            generate_report(form_type="eea2", report_year=2026, period_start=self.period_start, period_end=self.period_end)

    def test_generate_succeeds_once_ready(self):
        EmployerConfig.objects.create(
            trade_name="X", dti_registration_number="1", paye_sars_number="1", uif_reference_number="1",
            ee_reference_number="1", ceo_name="CEO", ee_senior_manager_name="EE", business_type="state_owned_enterprise",
        )
        EEQuestionnaire.objects.create(report_year=2026)
        report = generate_report(form_type="eea2", report_year=2026, period_start=self.period_start, period_end=self.period_end)
        self.assertEqual(report.version, 1)
        self.assertEqual(report.status, EEReport.Status.DRAFT)
        self.assertIn("workforce_profile", report.data)

    def test_regenerating_supersedes_the_prior_unsigned_version(self):
        EmployerConfig.objects.create(
            trade_name="X", dti_registration_number="1", paye_sars_number="1", uif_reference_number="1",
            ee_reference_number="1", ceo_name="CEO", ee_senior_manager_name="EE", business_type="state_owned_enterprise",
        )
        EEQuestionnaire.objects.create(report_year=2026)
        v1 = generate_report(form_type="eea2", report_year=2026, period_start=self.period_start, period_end=self.period_end)
        v2 = generate_report(form_type="eea2", report_year=2026, period_start=self.period_start, period_end=self.period_end)
        v1.refresh_from_db()
        self.assertEqual(v1.status, EEReport.Status.SUPERSEDED)
        self.assertEqual(v2.version, 2)

    def test_regenerating_does_not_touch_a_signed_off_version(self):
        EmployerConfig.objects.create(
            trade_name="X", dti_registration_number="1", paye_sars_number="1", uif_reference_number="1",
            ee_reference_number="1", ceo_name="CEO", ee_senior_manager_name="EE", business_type="state_owned_enterprise",
        )
        EEQuestionnaire.objects.create(report_year=2026)
        v1 = generate_report(form_type="eea2", report_year=2026, period_start=self.period_start, period_end=self.period_end)
        submit_for_review(v1)
        ee_manager_approve(v1, actor=None)
        sign_off(v1, actor=None)
        v2 = generate_report(form_type="eea2", report_year=2026, period_start=self.period_start, period_end=self.period_end)
        v1.refresh_from_db()
        self.assertEqual(v1.status, EEReport.Status.SIGNED_OFF)
        self.assertEqual(v2.version, 2)


class ApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.junior, self.grade, self.junior_grade, self.location = _seed_reference_data()
        EmployerConfig.objects.create(
            trade_name="X", dti_registration_number="1", paye_sars_number="1", uif_reference_number="1",
            ee_reference_number="1", ceo_name="CEO", ee_senior_manager_name="EE", business_type="state_owned_enterprise",
        )
        EEQuestionnaire.objects.create(report_year=2026)
        self.report = generate_report(
            form_type="eea2", report_year=2026, period_start=date(2025, 9, 1), period_end=date(2026, 8, 31)
        )

    def test_cannot_review_a_draft_directly(self):
        with self.assertRaises(ApprovalError):
            ee_manager_approve(self.report, actor=None)

    def test_cannot_sign_off_before_review(self):
        with self.assertRaises(ApprovalError):
            sign_off(self.report, actor=None)

    def test_full_happy_path(self):
        submit_for_review(self.report)
        self.assertEqual(self.report.status, EEReport.Status.PENDING_EE_REVIEW)
        ee_manager_approve(self.report, actor=None)
        self.assertEqual(self.report.status, EEReport.Status.PENDING_SIGNOFF)
        sign_off(self.report, actor=None, place="Johannesburg")
        self.assertEqual(self.report.status, EEReport.Status.SIGNED_OFF)
        self.assertEqual(self.report.signed_off_place, "Johannesburg")

    def test_cannot_double_submit(self):
        submit_for_review(self.report)
        with self.assertRaises(ApprovalError):
            submit_for_review(self.report)


class ValidationTests(TestCase):
    def test_missing_employer_fields_are_individually_reported(self):
        EmployerConfig.objects.create(trade_name="X")  # missing everything else
        issues = validate_report_readiness(
            form_type="eea2", report_year=2026, period_start=date(2025, 9, 1), period_end=date(2026, 8, 31)
        )
        self.assertTrue(any("missing" in issue.lower() for issue in issues))

    def test_eea4_requires_matching_eea2_first(self):
        EmployerConfig.objects.create(
            trade_name="X", dti_registration_number="1", paye_sars_number="1", uif_reference_number="1",
            ee_reference_number="1", ceo_name="CEO", ee_senior_manager_name="EE", business_type="state_owned_enterprise",
        )
        EEQuestionnaire.objects.create(report_year=2026)
        dept, level, junior, grade, junior_grade, location = _seed_reference_data()
        emp = _hire("E001", dept=dept, level=level, grade=grade, location=location)
        RemunerationRecord.objects.create(
            employee=emp, period_start=date(2025, 9, 1), period_end=date(2026, 8, 31), fixed_remuneration=300000,
        )
        issues = validate_report_readiness(
            form_type="eea4", report_year=2026, period_start=date(2025, 9, 1), period_end=date(2026, 8, 31)
        )
        self.assertTrue(any("EEA2" in issue for issue in issues))


class ExportTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.junior, self.grade, self.junior_grade, self.location = _seed_reference_data()
        _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        EmployerConfig.objects.create(
            trade_name="X", dti_registration_number="1", paye_sars_number="1", uif_reference_number="1",
            ee_reference_number="1", ceo_name="CEO", ee_senior_manager_name="EE", business_type="state_owned_enterprise",
        )
        EEQuestionnaire.objects.create(report_year=2026)
        self.report = generate_report(
            form_type="eea2", report_year=2026, period_start=date(2025, 9, 1), period_end=date(2026, 8, 31)
        )

    def test_csv_export_contains_workforce_profile_section(self):
        text = export.to_csv(self.report)
        self.assertIn("Workforce Profile", text)

    def test_excel_export_produces_nonempty_bytes(self):
        self.assertGreater(len(export.to_excel(self.report)), 0)

    def test_pdf_export_produces_a_valid_pdf_header(self):
        pdf_bytes = export.to_pdf(self.report)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_xml_export_is_well_formed(self):
        import xml.etree.ElementTree as ET

        xml_text = export.to_xml(self.report)
        root = ET.fromstring(xml_text)
        self.assertEqual(root.tag, "eea2")
        self.assertEqual(root.get("year"), "2026")
