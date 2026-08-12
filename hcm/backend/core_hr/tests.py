import io
from datetime import date

import openpyxl
from django.db.utils import IntegrityError
from django.test import TestCase

from .data_quality import run_data_quality_checks
from .imports import import_employees_csv, import_employees_xlsx
from .models import (
    DataQualityException,
    Department,
    Employee,
    EmployeeVersion,
    EmploymentEvent,
    JobGrade,
    Location,
    OccupationalLevel,
)


def _seed_reference_data():
    dept_a = Department.objects.create(name="Engineering", code="ENG")
    dept_b = Department.objects.create(name="Finance", code="FIN")
    level_top = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level_top)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept_a, dept_b, level_top, grade, location


class EmployeeVersionHistoryTests(TestCase):
    """Sprint 1 acceptance criterion: a report run for a prior date reflects
    historical values as of that date."""

    def test_as_at_query_reflects_historical_values(self):
        dept_a, dept_b, level_top, grade, location = _seed_reference_data()

        employee = Employee.objects.hire(
            employee_number="E0001",
            first_name="Thandiwe",
            last_name="Nkosi",
            date_of_birth=date(1990, 1, 1),
            work_email="thandiwe.nkosi@example.com",
            hire_date=date(2024, 1, 1),
            department=dept_a,
            occupational_level=level_top,
            job_grade=grade,
            location=location,
        )

        employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.TRANSFER,
            effective_date=date(2025, 1, 1),
            department=dept_b,
        )

        # as-at a date before the transfer -> old department
        version_before = employee.version_as_at(date(2024, 6, 1))
        self.assertEqual(version_before.department, dept_a)

        # as-at a date after the transfer -> new department
        version_after = employee.version_as_at(date(2025, 6, 1))
        self.assertEqual(version_after.department, dept_b)

        # current version matches the latest state
        self.assertEqual(employee.current_version.department, dept_b)

        # exactly one EmploymentEvent recorded, linking the two versions
        event = employee.lifecycle_events.get(event_type=EmploymentEvent.EventType.TRANSFER)
        self.assertEqual(event.from_version, version_before)
        self.assertEqual(event.to_version, version_after)

    def test_termination_closes_version_without_opening_a_new_one(self):
        dept_a, _, level_top, grade, location = _seed_reference_data()
        employee = Employee.objects.hire(
            employee_number="E0002",
            first_name="Sipho",
            last_name="Dlamini",
            date_of_birth=date(1985, 5, 5),
            work_email="sipho.dlamini@example.com",
            hire_date=date(2023, 1, 1),
            department=dept_a,
            occupational_level=level_top,
            job_grade=grade,
            location=location,
        )

        event = employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.TERMINATION,
            effective_date=date(2026, 1, 1),
            termination_reason=EmploymentEvent.TerminationReason.RESIGNATION,
        )

        self.assertIsNone(event.to_version)
        self.assertIsNone(employee.version_as_at(date(2026, 6, 1)))
        # still resolvable as at a date while employed
        self.assertIsNotNone(employee.version_as_at(date(2024, 1, 1)))


class BulkImportTests(TestCase):
    """Sprint 1 acceptance criterion: bulk import flags invalid/incomplete
    rows without corrupting existing data."""

    def setUp(self):
        self.dept_a, self.dept_b, self.level_top, self.grade, self.location = _seed_reference_data()
        self.existing = Employee.objects.hire(
            employee_number="E9999",
            first_name="Existing",
            last_name="Employee",
            date_of_birth=date(1980, 1, 1),
            work_email="existing.employee@example.com",
            hire_date=date(2020, 1, 1),
            department=self.dept_a,
            occupational_level=self.level_top,
            job_grade=self.grade,
            location=self.location,
        )

    def _csv(self, rows: list[dict]) -> io.StringIO:
        header = [
            "employee_number", "first_name", "last_name", "date_of_birth", "work_email",
            "hire_date", "department_code", "occupational_level_code", "job_grade_code",
            "location_code", "race", "gender", "disability_status",
        ]
        lines = [",".join(header)]
        for row in rows:
            lines.append(",".join(row.get(col, "") for col in header))
        return io.StringIO("\n".join(lines))

    def test_valid_rows_import_and_invalid_rows_are_flagged(self):
        stream = self._csv([
            {
                "employee_number": "E0010", "first_name": "Valid", "last_name": "One",
                "date_of_birth": "1990-01-01", "work_email": "valid.one@example.com",
                "hire_date": "2024-01-01", "department_code": "ENG",
                "occupational_level_code": "TOP", "job_grade_code": "G1",
                "location_code": "HO", "race": "african", "gender": "female",
                "disability_status": "no",
            },
            {
                # missing required last_name
                "employee_number": "E0011", "first_name": "Invalid",
                "date_of_birth": "1990-01-01", "work_email": "invalid.one@example.com",
                "hire_date": "2024-01-01", "department_code": "ENG",
                "occupational_level_code": "TOP", "location_code": "HO",
            },
            {
                # duplicate of the pre-existing employee
                "employee_number": "E9999", "first_name": "Dup", "last_name": "Licate",
                "date_of_birth": "1990-01-01", "work_email": "dup.licate@example.com",
                "hire_date": "2024-01-01", "department_code": "ENG",
                "occupational_level_code": "TOP", "location_code": "HO",
            },
            {
                # unknown department code
                "employee_number": "E0012", "first_name": "Bad", "last_name": "Dept",
                "date_of_birth": "1990-01-01", "work_email": "bad.dept@example.com",
                "hire_date": "2024-01-01", "department_code": "NOPE",
                "occupational_level_code": "TOP", "location_code": "HO",
            },
        ])

        result = import_employees_csv(stream)

        self.assertEqual(result.imported_count, 1)
        self.assertIn("E0010", result.imported_employee_numbers)
        self.assertEqual(result.error_count, 3)

        # the valid row was actually created
        self.assertTrue(Employee.objects.filter(employee_number="E0010").exists())
        # the invalid rows were not
        self.assertFalse(Employee.objects.filter(employee_number="E0011").exists())
        self.assertFalse(Employee.objects.filter(employee_number="E0012").exists())

        # pre-existing employee's data is untouched by the failed duplicate row
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.first_name, "Existing")
        self.assertEqual(Employee.objects.filter(employee_number="E9999").count(), 1)

    def test_missing_job_grade_imports_successfully_and_is_flagged_as_data_quality_issue(self):
        stream = self._csv([
            {
                "employee_number": "E0020", "first_name": "No", "last_name": "Grade",
                "date_of_birth": "1990-01-01", "work_email": "no.grade@example.com",
                "hire_date": "2024-01-01", "department_code": "ENG",
                "occupational_level_code": "TOP", "location_code": "HO",
            },
        ])

        result = import_employees_csv(stream)

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.error_count, 0)

        employee = Employee.objects.get(employee_number="E0020")
        self.assertIsNone(employee.current_version.job_grade)
        self.assertTrue(
            DataQualityException.objects.filter(
                employee=employee,
                exception_type=DataQualityException.ExceptionType.MISSING_GRADE,
                resolved_at__isnull=True,
            ).exists()
        )
        self.assertTrue(
            DataQualityException.objects.filter(
                employee=employee,
                exception_type=DataQualityException.ExceptionType.MISSING_DEMOGRAPHICS,
                resolved_at__isnull=True,
            ).exists()
        )


class ExcelImportTests(TestCase):
    def setUp(self):
        self.dept_a, _, self.level_top, self.grade, self.location = _seed_reference_data()

    def test_valid_xlsx_row_imports(self):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        header = [
            "employee_number", "first_name", "last_name", "date_of_birth", "work_email",
            "hire_date", "department_code", "occupational_level_code", "job_grade_code",
            "location_code",
        ]
        sheet.append(header)
        sheet.append([
            "E0050", "Excel", "Row", date(1990, 1, 1), "excel.row@example.com",
            date(2024, 1, 1), "ENG", "TOP", "G1", "HO",
        ])
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)

        result = import_employees_xlsx(buffer)

        self.assertEqual(result.imported_count, 1)
        self.assertEqual(result.error_count, 0)
        self.assertTrue(Employee.objects.filter(employee_number="E0050").exists())


class DataQualityChecksTests(TestCase):
    def setUp(self):
        self.dept_a, _, self.level_top, self.grade, self.location = _seed_reference_data()

    def test_orphan_record_is_detected(self):
        # an Employee row created without any EmployeeVersion (e.g. a
        # partial/failed import) should be flagged, not silently ignored
        orphan = Employee.objects.create(
            employee_number="E0030",
            first_name="Orphan",
            last_name="Record",
            date_of_birth=date(1990, 1, 1),
            work_email="orphan.record@example.com",
            hire_date=date(2024, 1, 1),
        )

        run_data_quality_checks()

        self.assertTrue(
            DataQualityException.objects.filter(
                employee=orphan,
                exception_type=DataQualityException.ExceptionType.ORPHAN_RECORD,
                resolved_at__isnull=True,
            ).exists()
        )

    def test_exception_auto_resolves_once_fixed(self):
        employee = Employee.objects.hire(
            employee_number="E0031",
            first_name="Fix",
            last_name="Me",
            date_of_birth=date(1990, 1, 1),
            work_email="fix.me@example.com",
            hire_date=date(2024, 1, 1),
            department=self.dept_a,
            occupational_level=self.level_top,
            job_grade=None,
            location=self.location,
        )

        run_data_quality_checks()
        self.assertTrue(
            DataQualityException.objects.filter(
                employee=employee,
                exception_type=DataQualityException.ExceptionType.MISSING_GRADE,
                resolved_at__isnull=True,
            ).exists()
        )

        version = employee.current_version
        version.job_grade = self.grade
        version.save(update_fields=["job_grade"])

        run_data_quality_checks()
        self.assertFalse(
            DataQualityException.objects.filter(
                employee=employee,
                exception_type=DataQualityException.ExceptionType.MISSING_GRADE,
                resolved_at__isnull=True,
            ).exists()
        )
        self.assertTrue(
            DataQualityException.objects.filter(
                employee=employee,
                exception_type=DataQualityException.ExceptionType.MISSING_GRADE,
                resolved_at__isnull=False,
            ).exists()
        )


class EmployeeVersionConstraintTests(TestCase):
    def test_valid_to_must_be_after_valid_from(self):
        dept_a, _, level_top, grade, location = _seed_reference_data()
        employee = Employee.objects.create(
            employee_number="E0040",
            first_name="Bad",
            last_name="Range",
            date_of_birth=date(1990, 1, 1),
            work_email="bad.range@example.com",
            hire_date=date(2024, 1, 1),
        )
        with self.assertRaises(IntegrityError):
            EmployeeVersion.objects.create(
                employee=employee,
                valid_from=date(2024, 1, 1),
                valid_to=date(2023, 1, 1),
                department=dept_a,
                occupational_level=level_top,
                job_grade=grade,
                location=location,
                employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
                citizenship_status=EmployeeVersion.CitizenshipStatus.SA_CITIZEN_BIRTH_DESCENT,
            )
