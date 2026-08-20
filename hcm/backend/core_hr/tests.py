import io
from datetime import date
from unittest.mock import patch

import openpyxl
from django.db import IntegrityError, transaction
from django.test import TestCase
from establishment.models import Position

from .contracts import ContractDecisionError, decide_contract_action, recommend_contract_action
from .data_quality import run_data_quality_checks
from .imports import import_employees_csv, import_employees_xlsx
from .models import (
    ContractRenewalDecision,
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


class EmployeeVersionPositionTests(TestCase):
    def setUp(self):
        self.dept_a, _, self.level_top, self.grade, self.location = _seed_reference_data()
        self.position = Position.objects.create(
            post_number="P-00001", title="Engineer", department=self.dept_a, occupational_level=self.level_top,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )

    def test_hire_can_link_a_position(self):
        employee = Employee.objects.hire(
            employee_number="E0050", first_name="Pos", last_name="Itioned", date_of_birth=date(1990, 1, 1),
            work_email="pos.itioned@example.com", hire_date=date(2024, 1, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location, position=self.position,
        )
        self.assertEqual(employee.current_version.position_id, self.position.id)

    def test_hire_without_a_position_still_works(self):
        """Backward compatibility: every existing caller (bulk import, seed
        data, other tests) omits position entirely."""
        employee = Employee.objects.hire(
            employee_number="E0051", first_name="No", last_name="Position", date_of_birth=date(1990, 1, 1),
            work_email="no.position@example.com", hire_date=date(2024, 1, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location,
        )
        self.assertIsNone(employee.current_version.position_id)

    def test_position_carries_forward_across_a_promotion(self):
        """Regression guard: VERSION_CARRY_FIELDS must include 'position',
        or a promotion/transfer/grade-change silently vacates the post even
        though the employee never actually left it."""
        employee = Employee.objects.hire(
            employee_number="E0052", first_name="Carried", last_name="Forward", date_of_birth=date(1990, 1, 1),
            work_email="carried.forward@example.com", hire_date=date(2024, 1, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location, position=self.position,
        )
        employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.GRADE_CHANGE, effective_date=date(2025, 1, 1),
        )
        self.assertEqual(employee.current_version.position_id, self.position.id)

    def test_two_current_versions_cannot_share_one_position(self):
        """The whole derived-occupancy design — Position.current_occupant,
        is_vacant, Position.objects.vacant(), the hire flow's position
        assignment, and recruitment's vacancy check — assumes at most one
        current occupant per post. current_occupant's .first() would
        silently pick one of two concurrent claimants rather than surface
        the violation, so the schema has to be what enforces it."""
        Employee.objects.hire(
            employee_number="E0053", first_name="First", last_name="Occupant", date_of_birth=date(1990, 1, 1),
            work_email="first.occupant@example.com", hire_date=date(2024, 1, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location, position=self.position,
        )
        with self.assertRaises(IntegrityError):
            Employee.objects.hire(
                employee_number="E0054", first_name="Second", last_name="Occupant", date_of_birth=date(1991, 1, 1),
                work_email="second.occupant@example.com", hire_date=date(2024, 6, 1), department=self.dept_a,
                occupational_level=self.level_top, job_grade=self.grade, location=self.location,
                position=self.position,
            )

    def test_a_position_freed_by_a_termination_can_be_reoccupied(self):
        """The constraint is partial (valid_to IS NULL) on purpose: a post
        persists across incumbents (design spec §2.1/§4.4), so the closed
        version of a leaver must never block the next hire into their old
        post."""
        leaver = Employee.objects.hire(
            employee_number="E0055", first_name="Departing", last_name="Occupant", date_of_birth=date(1990, 1, 1),
            work_email="departing.occupant@example.com", hire_date=date(2024, 1, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location, position=self.position,
        )
        leaver.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.TERMINATION, effective_date=date(2025, 1, 1),
        )
        successor = Employee.objects.hire(
            employee_number="E0056", first_name="Next", last_name="Occupant", date_of_birth=date(1991, 1, 1),
            work_email="next.occupant@example.com", hire_date=date(2025, 2, 1), department=self.dept_a,
            occupational_level=self.level_top, job_grade=self.grade, location=self.location, position=self.position,
        )
        self.assertEqual(successor.current_version.position_id, self.position.id)
        self.assertEqual(self.position.employee_versions.count(), 2)


class ContractEndDateFieldTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=99)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.employee = Employee.objects.hire(
            employee_number="E900", first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email="contractor@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=date(2026, 12, 31),
        )

    def test_contract_end_date_stored_on_hire(self):
        self.assertEqual(self.employee.current_version.contract_end_date, date(2026, 12, 31))

    def test_contract_end_date_carries_forward_on_unrelated_promotion(self):
        self.employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.PROMOTION, effective_date=date(2026, 6, 1),
            job_title="Senior Contractor",
        )
        self.assertEqual(self.employee.current_version.contract_end_date, date(2026, 12, 31))

    def test_contract_end_date_null_for_permanent_employee(self):
        permanent = Employee.objects.hire(
            employee_number="E901", first_name="Test", last_name="Permanent",
            date_of_birth=date(1990, 1, 1), work_email="permanent@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.assertIsNone(permanent.current_version.contract_end_date)


class ContractRenewalDecisionModelTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=98)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.manager = Employee.objects.hire(
            employee_number="E800", first_name="Line", last_name="Manager",
            date_of_birth=date(1980, 1, 1), work_email="linemanager@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.employee = Employee.objects.hire(
            employee_number="E900", first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email="contractor2@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=date(2026, 12, 31), manager=self.manager,
        )

    def test_one_decision_row_per_version(self):
        version = self.employee.current_version
        ContractRenewalDecision.objects.create(employee_version=version, status=ContractRenewalDecision.Status.RECOMMENDED)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ContractRenewalDecision.objects.create(employee_version=version, status=ContractRenewalDecision.Status.RECOMMENDED)

    def test_no_row_created_by_default(self):
        self.assertFalse(ContractRenewalDecision.objects.filter(employee_version=self.employee.current_version).exists())


class ContractDecisionServiceTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="ENG", name="Engineering")
        self.level = OccupationalLevel.objects.create(code="P", name="Professional", order=97)
        self.location = Location.objects.create(code="JHB", name="Johannesburg", province="Gauteng")
        self.manager = Employee.objects.hire(
            employee_number="E800", first_name="Line", last_name="Manager",
            date_of_birth=date(1980, 1, 1), work_email="linemanager3@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.hr_admin = Employee.objects.hire(
            employee_number="E801", first_name="HR", last_name="Admin",
            date_of_birth=date(1980, 1, 1), work_email="hradmin3@sentech.example.com",
            hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.PERMANENT,
        )
        self.employee = Employee.objects.hire(
            employee_number="E900", first_name="Test", last_name="Contractor",
            date_of_birth=date(1990, 1, 1), work_email="contractor3@sentech.example.com",
            hire_date=date(2026, 1, 1), department=self.dept, occupational_level=self.level,
            location=self.location, employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
            contract_end_date=date(2026, 12, 31), manager=self.manager,
        )
        self.version = self.employee.current_version

    def test_recommend_creates_a_recommended_row(self):
        decision = recommend_contract_action(
            self.version, actor=self.manager, action=ContractRenewalDecision.Action.RENEW,
            comment="Team still needs them.", end_date=date(2027, 12, 31),
        )
        self.assertEqual(decision.status, ContractRenewalDecision.Status.RECOMMENDED)
        self.assertEqual(decision.recommended_by, self.manager)
        self.assertEqual(decision.recommended_end_date, date(2027, 12, 31))

    def test_recommend_twice_raises(self):
        recommend_contract_action(self.version, actor=self.manager, action=ContractRenewalDecision.Action.RENEW, end_date=date(2027, 12, 31))
        with self.assertRaises(ContractDecisionError):
            recommend_contract_action(self.version, actor=self.manager, action=ContractRenewalDecision.Action.LET_LAPSE)

    def test_decide_without_a_prior_recommendation_is_allowed(self):
        decision = decide_contract_action(
            self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.CONVERT_PERMANENT,
        )
        self.assertEqual(decision.status, ContractRenewalDecision.Status.DECIDED)
        self.assertIsNone(decision.recommended_action)

    def test_decide_renew_creates_a_new_version_and_closes_the_old_one(self):
        decide_contract_action(
            self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.RENEW,
            end_date=date(2027, 12, 31),
        )
        self.version.refresh_from_db()
        self.assertIsNotNone(self.version.valid_to)
        new_version = self.employee.current_version
        self.assertEqual(new_version.contract_end_date, date(2027, 12, 31))
        self.assertEqual(new_version.employment_status, EmployeeVersion.EmploymentStatus.FIXED_TERM)
        decision = ContractRenewalDecision.objects.get(employee_version=self.version)
        self.assertEqual(decision.resulting_employee_version, new_version)
        event = EmploymentEvent.objects.get(from_version=self.version)
        self.assertEqual(event.event_type, EmploymentEvent.EventType.CONTRACT_RENEWAL)

    def test_decide_convert_permanent_clears_the_end_date(self):
        decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.CONVERT_PERMANENT)
        new_version = self.employee.current_version
        self.assertEqual(new_version.employment_status, EmployeeVersion.EmploymentStatus.PERMANENT)
        self.assertIsNone(new_version.contract_end_date)
        event = EmploymentEvent.objects.get(from_version=self.version)
        self.assertEqual(event.event_type, EmploymentEvent.EventType.CONTRACT_CONVERSION)

    def test_decide_let_lapse_terminates_with_no_new_version(self):
        decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.LET_LAPSE)
        self.assertIsNone(self.employee.current_version)
        event = EmploymentEvent.objects.get(from_version=self.version)
        self.assertEqual(event.event_type, EmploymentEvent.EventType.TERMINATION)
        self.assertEqual(event.termination_reason, EmploymentEvent.TerminationReason.CONTRACT_END)
        decision = ContractRenewalDecision.objects.get(employee_version=self.version)
        self.assertIsNone(decision.resulting_employee_version)

    def test_decide_twice_raises(self):
        decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.CONVERT_PERMANENT)
        with self.assertRaises(ContractDecisionError):
            decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.LET_LAPSE)

    def test_decide_accepts_and_can_override_a_recommendation(self):
        recommend_contract_action(self.version, actor=self.manager, action=ContractRenewalDecision.Action.RENEW, end_date=date(2027, 6, 30))
        decide_contract_action(self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.RENEW, end_date=date(2027, 12, 31))
        new_version = self.employee.current_version
        self.assertEqual(new_version.contract_end_date, date(2027, 12, 31))

    def test_recommend_rejects_invalid_action(self):
        with self.assertRaises(ContractDecisionError):
            recommend_contract_action(self.version, actor=self.manager, action="not_a_real_action")
        self.assertFalse(
            ContractRenewalDecision.objects.filter(employee_version=self.version).exists()
        )

    def test_decide_rolls_back_lifecycle_changes_if_decision_save_fails(self):
        """Regression guard for atomicity: decide_contract_action performs
        get_or_create (write #1), apply_lifecycle_event (write #2), then
        decision.save() (write #3). If the last write fails, the earlier
        writes must not be left committed -- otherwise the employee's
        contract could be silently renewed/converted/terminated while the
        ContractRenewalDecision row is stuck at RECOMMENDED, and a retry
        would not be blocked by the status check (it isn't DECIDED yet),
        compounding the inconsistency."""
        recommend_contract_action(
            self.version, actor=self.manager, action=ContractRenewalDecision.Action.RENEW,
            end_date=date(2027, 12, 31),
        )
        with patch.object(ContractRenewalDecision, "save", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                decide_contract_action(
                    self.version, actor=self.hr_admin, action=ContractRenewalDecision.Action.RENEW,
                    end_date=date(2027, 12, 31),
                )
        self.version.refresh_from_db()
        self.assertIsNone(self.version.valid_to)
        self.assertEqual(self.employee.current_version, self.version)
        self.assertFalse(EmploymentEvent.objects.filter(from_version=self.version).exists())
        decision = ContractRenewalDecision.objects.get(employee_version=self.version)
        self.assertEqual(decision.status, ContractRenewalDecision.Status.RECOMMENDED)
