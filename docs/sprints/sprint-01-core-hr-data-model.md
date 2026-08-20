[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

## Sprint 1 — Core HR Data Model
**Goal:** Single source-of-truth employee table with history support.
**Status: done** (2026-08-12) — see `hcm/backend/core_hr/`. Pay grade→SAP linkage remains open per action A10; consent-record tracking for self-ID is Sprint 2 scope (rbac_audit), not this sprint.

**Tasks:**
- [x] Design and migrate `employees` table: demographics (race, gender, disability, self-ID source fields), job level, department, pay grade, employment dates — `core_hr/models.py`: `Employee` (identity) + `EmployeeVersion` (time-varying attributes)
- [x] Add as-at-date/history versioning (effective-dated rows, ADR-002) — `EmployeeVersion.valid_from/valid_to` + `EmployeeVersionQuerySet.as_at()`; full change audit via `django-simple-history` on every model
- [x] Design org structure tables: department, reporting lines, job levels — `Department` (self-referencing tree), `OccupationalLevel` (seeded with the 6 statutory EEA levels), `JobGrade`, `Location`; reporting line via `EmployeeVersion.manager`
- [x] Build bulk import (CSV/Excel) with validation rules — `core_hr/imports.py` (`import_employees_csv`, `import_employees_xlsx`) + `manage.py import_employees <file>`
- [x] Build data-quality exception detection (missing grade, missing demographics, orphan records) — `core_hr/data_quality.py::run_data_quality_checks()`, auto-resolves once fixed
- [x] **(added, gap F1)** `EmploymentEvent` lifecycle model: hire / promotion / transfer / grade_change / termination (with EEA2 movement reason codes) / contract_conversion — `Employee.apply_lifecycle_event()`; `Employee.objects.hire()` is the single hire-to-record entry point Sprint 4 recruitment will reuse

**Acceptance criteria:**
- [x] Given an employee record is updated, when a report is run for a prior date, then it reflects historical values as of that date. — `core_hr/tests.py::EmployeeVersionHistoryTests`
- [x] Bulk import flags invalid/incomplete rows without corrupting existing data. — `core_hr/tests.py::BulkImportTests` (each row imports in its own savepoint)
- [x] **(added)** A terminated employee is excluded from current-headcount views but appears in as-at historical reports. — `EmployeeVersionHistoryTests.test_termination_closes_version_without_opening_a_new_one`

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, `migrate`, and `manage.py test core_hr` all pass (8/8 tests). CI (`.github/workflows/hcm-ci.yml`) runs the same checks on every push/PR touching `HR_system/hcm/**`.

