from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

import openpyxl
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction

from .data_quality import run_data_quality_checks
from .models import Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel

REQUIRED_COLUMNS = (
    "employee_number", "first_name", "last_name", "date_of_birth", "work_email",
    "hire_date", "department_code", "occupational_level_code", "location_code",
)


@dataclass
class RowError:
    row_number: int
    employee_number: str
    reason: str


@dataclass
class ImportResult:
    imported_employee_numbers: list[str] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)

    @property
    def imported_count(self) -> int:
        return len(self.imported_employee_numbers)

    @property
    def error_count(self) -> int:
        return len(self.errors)


def import_employees_csv(text_stream) -> ImportResult:
    """Bulk-loads employees from a CSV (Sprint 1 task). See `_run_import`
    for the shared validation/import pipeline also used by
    `import_employees_xlsx`."""
    reader = csv.DictReader(text_stream)

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing_columns:
        raise ValueError(f"CSV is missing required column(s): {', '.join(missing_columns)}")

    return _run_import(reader)


def import_employees_xlsx(file_obj) -> ImportResult:
    """Bulk-loads employees from an .xlsx workbook: first sheet, header row
    first, one employee per subsequent row. Same validation pipeline as
    `import_employees_csv`."""
    workbook = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
    sheet = workbook.active
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        header = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    except StopIteration:
        raise ValueError("Workbook is empty")

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing_columns:
        raise ValueError(f"Workbook is missing required column(s): {', '.join(missing_columns)}")

    return _run_import(_xlsx_row_dicts(header, rows_iter))


def _xlsx_row_dicts(header: list[str], rows_iter) -> Iterable[dict]:
    for values in rows_iter:
        if values is None or all(v is None for v in values):
            continue
        row = {}
        for col, value in zip(header, values):
            if value is None:
                row[col] = ""
            elif hasattr(value, "strftime"):
                row[col] = value.strftime("%Y-%m-%d")
            elif isinstance(value, float) and value.is_integer():
                row[col] = str(int(value))
            else:
                row[col] = str(value).strip()
        yield row


def _run_import(rows: Iterable[dict]) -> ImportResult:
    """Validates and imports each row independently in its own savepoint:
    an invalid row is skipped and reported without rolling back rows
    already committed. Soft-missing fields (job grade, demographics)
    import successfully and surface afterward as DataQualityException
    records rather than blocking the row."""
    result = ImportResult()
    pending_managers: list[tuple[str, str]] = []

    for row_number, row in enumerate(rows, start=2):  # header occupies row 1
        employee_number = (row.get("employee_number") or "").strip()
        try:
            with transaction.atomic():
                _import_row(row)
        except (ValueError, ValidationError, IntegrityError) as exc:
            result.errors.append(
                RowError(row_number=row_number, employee_number=employee_number, reason=str(exc))
            )
            continue

        result.imported_employee_numbers.append(employee_number)
        manager_number = (row.get("manager_employee_number") or "").strip()
        if manager_number:
            pending_managers.append((employee_number, manager_number))

    for employee_number, manager_number in pending_managers:
        try:
            employee = Employee.objects.get(employee_number=employee_number)
            manager = Employee.objects.get(employee_number=manager_number)
        except Employee.DoesNotExist:
            continue
        version = employee.current_version
        if version is not None:
            version.manager = manager
            version.save(update_fields=["manager"])

    run_data_quality_checks()
    return result


def _import_row(row: dict) -> None:
    employee_number = _required(row, "employee_number")
    if Employee.objects.filter(employee_number=employee_number).exists():
        raise ValueError(f"employee_number '{employee_number}' already exists")

    first_name = _required(row, "first_name")
    last_name = _required(row, "last_name")
    date_of_birth = _parse_date(row, "date_of_birth")
    hire_date = _parse_date(row, "hire_date")
    if date_of_birth >= hire_date:
        raise ValueError("date_of_birth must be before hire_date")

    work_email = _required(row, "work_email")
    validate_email(work_email)
    if Employee.objects.filter(work_email=work_email).exists():
        raise ValueError(f"work_email '{work_email}' already exists")

    department = _lookup(Department, "code", _required(row, "department_code"), "department_code")
    occupational_level = _lookup(
        OccupationalLevel, "code", _required(row, "occupational_level_code"), "occupational_level_code"
    )
    location = _lookup(Location, "code", _required(row, "location_code"), "location_code")

    job_grade = None
    job_grade_code = (row.get("job_grade_code") or "").strip()
    if job_grade_code:
        job_grade = _lookup(JobGrade, "code", job_grade_code, "job_grade_code")

    employment_status = _choice(
        row, "employment_status", EmployeeVersion.EmploymentStatus, EmployeeVersion.EmploymentStatus.PERMANENT
    )
    citizenship_status = _choice(
        row, "citizenship_status", EmployeeVersion.CitizenshipStatus,
        EmployeeVersion.CitizenshipStatus.SA_CITIZEN_BIRTH_DESCENT,
    )
    race = _choice(row, "race", EmployeeVersion.Race, EmployeeVersion.Race.NOT_DISCLOSED)
    gender = _choice(row, "gender", EmployeeVersion.Gender, EmployeeVersion.Gender.NOT_DISCLOSED)
    disability_status = _choice(
        row, "disability_status", EmployeeVersion.DisabilityStatus, EmployeeVersion.DisabilityStatus.NOT_DISCLOSED
    )

    Employee.objects.hire(
        employee_number=employee_number,
        first_name=first_name,
        last_name=last_name,
        preferred_name=(row.get("preferred_name") or "").strip(),
        national_id_number=(row.get("national_id_number") or "").strip(),
        date_of_birth=date_of_birth,
        work_email=work_email,
        personal_email=(row.get("personal_email") or "").strip(),
        phone=(row.get("phone") or "").strip(),
        hire_date=hire_date,
        department=department,
        occupational_level=occupational_level,
        job_grade=job_grade,
        location=location,
        employment_status=employment_status,
        citizenship_status=citizenship_status,
        race=race,
        gender=gender,
        disability_status=disability_status,
        race_source=EmployeeVersion.DemographicSource.IMPORTED,
        disability_source=EmployeeVersion.DemographicSource.IMPORTED,
    )


def _required(row: dict, column: str) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"'{column}' is required")
    return value


def _parse_date(row: dict, column: str):
    value = _required(row, column)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"'{column}' must be YYYY-MM-DD, got '{value}'")


def _lookup(model, field_name: str, value: str, column: str):
    try:
        return model.objects.get(**{f"{field_name}__iexact": value})
    except model.DoesNotExist:
        raise ValueError(f"Unknown {column} '{value}'")


def _choice(row: dict, column: str, choices_cls, default):
    value = (row.get(column) or "").strip()
    if not value:
        return default
    for member in choices_cls:
        if member.value == value.lower():
            return member
    raise ValueError(f"'{column}' has invalid value '{value}'")
