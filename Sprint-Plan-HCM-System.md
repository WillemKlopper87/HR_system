# Sprint Plan: Full-Scope HCM System (Agent-Ready)

**Purpose:** Consolidates the PRD, Project Plan, and Technical Architecture into a single sequential, sprint-phased backlog an agent can execute against. Sprints are 2 weeks each, sequential by default (single build stream). If multiple parallel agents/engineers are available, Sprints 4–12 (the talent tracks) can be split across them per the Project Plan's Phase 2 parallelization note.

**Architecture baseline (do not deviate without a new ADR):** Modular monolith. React frontend, single backend (Django/Laravel/Node), single PostgreSQL database, one `employees` table as source of truth, one shared RBAC + audit-logging layer used by every module.

**Non-negotiable sequencing rule:** Sprints 1–3 (Core HR + RBAC/audit foundation) must complete before any other module starts. Every later module's data model has a foreign key back to `employees`.

---

## Sprint 0 — Discovery & Environment Setup
**Goal:** Confirm decisions, define data dictionary, stand up scaffolding.

**Tasks:**
- [ ] Confirm legal/country scope (SA-only vs. broader) and EE designated-employer status
- [ ] Identify existing systems/spreadsheets holding recruitment, performance, learning, compensation, EE data
- [ ] Obtain latest official EEA2/EEA4 form specs and DEL submission file format
- [ ] Draft cross-module data dictionary (fields, types, sensitivity classification per field)
- [ ] Decide: real vs. synthetic data for initial build/testing
- [ ] Decide: Assessments — integrate 3rd-party provider vs. build internal (default recommendation: integrate; see Architecture)
- [ ] Shortlist 1–2 assessment providers with documented APIs if integrating
- [ ] Decide: parallel or sequential build for talent tracks (affects sprint numbering below)
- [ ] Set up repo, CI/CD pipeline, PostgreSQL instance (dev/staging), base app scaffold (chosen framework)
- [ ] Define role list for RBAC (e.g., HR admin, EE manager, line manager, employee, recruiter, comp manager, auditor)

**Exit criteria:** Signed-off data dictionary; environment provisioned; open decisions above resolved or explicitly deferred with an owner.

---

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

---

## Sprint 2 — RBAC & Audit Foundation
**Goal:** Shared access-control and audit layer every later module will reuse.
**Status: done** (2026-08-12) — see `hcm/backend/rbac_audit/`. Scheduled retention-rule execution (the `RetentionRule` model exists; the Celery job that acts on it doesn't yet) and the real Employee list/detail UI are explicitly deferred to their own sprints (post-Sprint-16 hardening, and Sprint 3, respectively) — not omissions.

**Tasks:**
- [x] Implement role-based access control at the API layer (not just UI) — `rbac_audit/permissions.py` (`active_roles_for`, `can_access_tier`, `has_row_access`) + `rbac_audit/drf.py` (`RowScopePermission`, `TieredModelSerializer`, `row_scoped_queryset`), proven end-to-end via `core_hr`'s `EmployeeVersionViewSet`
- [x] Define per-field sensitivity rules (demographics/pay visible only to specific roles; aggregated-only for line managers) — `rbac_audit/tiers.py::FIELD_TIERS` (the declarative P/I/S/R map from `Data-Dictionary.md`) + the 8-role grant matrix from `RBAC-Roles.md` seeded via migration `0002_seed_roles`; line_manager's `own_team` scope has no individual Sensitive-tier read (full aggregate dashboards are Sprint 3)
- [x] Implement audit logging: who accessed/edited which sensitive field, when — `rbac_audit/models.py::AuditLogEntry` (append-only — `save()`/`delete()` raise after creation) + `rbac_audit/audit.py::log_access()`; fires on every S/R-tier field read (`TieredModelSerializer`) and every row-scope denial (`RowScopePermission`)
- [x] Build consent-tracking mechanism for demographic self-ID — `rbac_audit/models.py::ConsentRecord` (POPIA lawful-basis register) + `rbac_audit/consent.py` (`record_consent`, `withdraw_consent`, `has_active_consent`); Sprint 15's ESS UI will be its primary caller
- [x] Write RBAC/audit test suite (regression baseline for every future module) — `rbac_audit/tests.py`, 22 tests

**Acceptance criteria:**
- [x] Unauthorized role attempting to access individual-level sensitive data is blocked and logged. — `EmployeeVersionApiTests.test_line_manager_blocked_from_outsider_and_denial_is_logged`, `test_employee_self_scope_blocked_from_colleague` (403 + `AuditLogEntry.Action.ACCESS_DENIED`)
- [x] Every sensitive-field read/write produces an audit record. — `EmployeeVersionApiTests.test_hr_admin_sees_sensitive_fields_and_access_is_logged`; consent grant/withdrawal audited in `ConsentTests`

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, `migrate`, and `manage.py test` all pass — 30/30 tests project-wide (8 core_hr + 22 rbac_audit). CI runs the same suite on every push.

---

## Sprint 3 — Core HR Dashboards & Admin UI
**Goal:** HR admins can manage and view core data; unblocks all downstream modules.

**Tasks:**
- [ ] Employee list/detail UI with RBAC-aware field visibility
- [ ] Org structure management UI
- [ ] Data-quality exception dashboard for HR to resolve
- [ ] Basic org-wide headcount dashboard (department, level, pay band, race, gender, disability) — early version of the equity dashboard, reused/extended in the EE Reporting sprints

**Exit criteria (end of Phase 1 / Core HR):** Core employee data live, RBAC/audit enforced, HR admin can manage records end-to-end. **This is the hard gate — do not start Sprint 4 until this passes UAT-lite (internal review).**

---

## Sprint 4–5 — Recruitment / ATS
**Goal:** Requisition-to-hire pipeline feeding directly into `employees`.

**Tasks:**
- [ ] Requisition creation and management (role, department, level, headcount)
- [ ] Applicant model with pipeline stages (applied → screened → interview → offer → hired/rejected)
- [ ] Applicant demographic capture with explicit consent flow
- [ ] Offer tracking and approval
- [ ] Hire → automatic `employees` record creation (no re-entry)
- [ ] Recruitment dashboard: pipeline status, time-to-fill, applicant demographics (feeds EE reporting later)

**Acceptance criteria:**
- Given an applicant is marked "hired," when the record is saved, then a new `employees` row is created with no manual re-entry.
- Applicant demographic data is only visible per RBAC rules defined in Sprint 2.

---

## Sprint 6–7 — Performance Management
**Goal:** Goal-setting and structured review cycles tied to `employees`.

**Tasks:**
- [ ] Goal-setting model (employee + manager)
- [ ] Configurable review cycle (annual/biannual) with launch/track/close workflow
- [ ] Manager and self-review forms
- [ ] Feedback capture (manager, peer)
- [ ] Review completion tracking dashboard (target: 90%+ completion visibility)

**Acceptance criteria:**
- HR admin can launch a review cycle org-wide and see live completion status.
- Performance ratings are access-restricted per RBAC (not visible to all managers by default).

---

## Sprint 8–9 — Learning & Development
**Goal:** Skills/certifications record per employee, org-wide skills visibility.

**Tasks:**
- [ ] Skills and certification model per employee
- [ ] Training record tracking (completed/in-progress)
- [ ] Org-wide skills inventory report (gap analysis by department/level)
- [ ] Manager view of team development plans

**Acceptance criteria:**
- Skills inventory covers imported/entered employees with no duplicate skill entries per person.

---

## Sprint 10–11 — Compensation & Benefits
**Goal:** Pay bands and a controlled compensation review workflow.

**Tasks:**
- [ ] Pay band definitions by job level (with history/versioning per Sprint 1 pattern)
- [ ] Compensation review workflow: manager proposes → approver reviews → sign-off
- [ ] Basic benefits election tracking
- [ ] Pay-data visibility restricted to comp manager/HR admin roles only (strict RBAC)

**Acceptance criteria:**
- Compensation adjustments outside a defined pay band trigger a flag/require override approval.
- Pay data is not visible to line managers unless explicitly granted.

---

## Sprint 12 — Assessments & Psychometric Testing (Integration Path)
**Goal:** Provider-agnostic assessment integration layer.

**Tasks:**
- [ ] Build internal interface: assign → redirect/embed to provider → receive results (webhook/API) → store
- [ ] Integrate shortlisted 3rd-party provider (from Sprint 0 decision) via SSO/deep-link
- [ ] Result ingestion into Recruitment (candidate) or L&D (employee) records
- [ ] Consent capture before assessment assignment
- [ ] Restrict result visibility per RBAC (treat as sensitive as demographic data)
- [ ] (Optional, if in scope) AI agent for assessment recommendation and plain-language result summarization — recommendation/summary only, not scoring or administration

**Acceptance criteria:**
- Assessment results land in the correct employee/applicant record without manual entry.
- Provider can be swapped by reconfiguring the integration layer, not rewriting it.

*(If Sprint 0 decided to build internally instead: replace this sprint with a dedicated discovery + psychometrician-consultation spike before any engineering — do not estimate internal build without that input.)*

---

## Sprint 13–14 — Equity / EE Reporting
**Goal:** Draft EEA2/EEA4 generation using data now enriched by Recruitment, Performance, Compensation.

**Tasks:**
- [ ] Validation engine: check report readiness against required fields
- [ ] Draft EEA2-style report generation
- [ ] Draft EEA4-style report generation
- [ ] Export to PDF/Excel/CSV/XML per official spec
- [ ] Approval workflow: draft → HR review → EE manager review → sign-off → archive
- [ ] Full equity dashboard (department, level, pay band, race, gender, disability) — extends Sprint 3's basic version
- [ ] EE target-vs-actual tracking (if in scope)

**Acceptance criteria:**
- Generated draft report matches official EEA field layout.
- Every generated report is versioned and archived with sign-off record.

---

## Sprint 15 — Employee Self-Service
**Goal:** Employees manage their own profile/consent/benefits/learning requests.

**Tasks:**
- [ ] Self-ID submission flow with consent tracking
- [ ] Profile update UI (employee-editable fields only)
- [ ] Benefits election self-service
- [ ] Learning enrollment requests

---

## Sprint 16–17 — Hardening & UAT
**Goal:** Production-pilot readiness across all modules.

**Tasks:**
- [ ] Full regression test suite across all modules
- [ ] Data-quality checks org-wide
- [ ] RBAC/permission penetration-style testing
- [ ] Export/report validation against official EEA specs
- [ ] User acceptance testing with HR, talent, and EE stakeholders
- [ ] Security/compliance sign-off

**Exit criteria:** UAT sign-off; system ready for production pilot use.

---

## Summary Timeline
| Sprints | Module | Duration |
|---|---|---|
| 0 | Discovery & Setup | 1 sprint (2 wks) |
| 1–3 | Core HR + RBAC/Audit (hard gate) | 3 sprints (6 wks) |
| 4–5 | Recruitment/ATS | 2 sprints (4 wks) |
| 6–7 | Performance Management | 2 sprints (4 wks) |
| 8–9 | Learning & Development | 2 sprints (4 wks) |
| 10–11 | Compensation & Benefits | 2 sprints (4 wks) |
| 12 | Assessments (integration path) | 1 sprint (2 wks) |
| 13–14 | Equity/EE Reporting | 2 sprints (4 wks) |
| 15 | Employee Self-Service | 1 sprint (2 wks) |
| 16–17 | Hardening & UAT | 2 sprints (4 wks) |
| **Total (sequential)** | | **~18 sprints / 36 weeks** |

If Sprints 4–12 (talent tracks + assessments) run across parallel workstreams instead, that block compresses from ~22 weeks to as little as ~6–8 weeks — reducing total timeline to roughly **20–24 weeks**, per the original Project Plan's parallelization note.

## Notes for the Executing Agent
- Do not start any module before its dependencies (per sprint order above) are complete — every table has an FK to `employees`.
- Reuse the Sprint 2 RBAC/audit implementation everywhere; do not build per-module access control.
- Flag any deviation from the modular-monolith architecture (e.g., wanting to split a module into a separate service) back to a human before proceeding — that's an ADR-level decision, not a sprint-level one.
- Sensitive fields (race, gender, disability, pay, performance ratings, assessment results) must always route through the Sprint 2 RBAC layer — treat this as a hard constraint, not a per-feature judgment call.
