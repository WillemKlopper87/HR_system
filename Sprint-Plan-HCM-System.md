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
**Status: done** (2026-08-12) — see `hcm/backend/core_hr/` (new API surface) and `hcm/frontend/src/`. Verified end-to-end in a real browser (login → employee list/detail → org structure CRUD → data-quality resolve → headcount dashboard) across all three seeded demo roles (hr_admin, line_manager, employee), not just via the test suite.

**Tasks:**
- [x] Employee list/detail UI with RBAC-aware field visibility — `EmployeeListPage`/`EmployeeDetailPage`; the UI renders exactly what the tiered serializer sends (present key → value, absent key → "Restricted" badge) rather than re-implementing the access decision client-side. New backend surface: `EmployeeViewSet` (`/api/v1/employees/`) reusing the Sprint 2 row-scope + field-tier pattern; `EmployeeVersionViewSet` gained `?employee=` and `?current=true` filters
- [x] Org structure management UI — `OrgStructurePage`: Department/JobGrade/Location CRUD (hr_admin-only writes, `IsHRAdminOrReadOnly`), OccupationalLevel shown read-only (statutory, not user-editable). New `DepartmentViewSet`/`JobGradeViewSet`/`LocationViewSet`/`OccupationalLevelViewSet`
- [x] Data-quality exception dashboard for HR to resolve — `DataQualityPage`; new `DataQualityExceptionViewSet` (`IsHRAdmin`-gated) with `resolve` and `run_checks` actions over the existing Sprint 1 `run_data_quality_checks()`
- [x] Basic org-wide headcount dashboard (department, level, pay band, race, gender, disability) — `HeadcountDashboardPage`; new `headcount_dashboard` aggregation endpoint with **small-cell suppression (n<5)** per RBAC-Roles.md standing rule 1 / gap C6, gated on holding an ALL-row-scope role with Sensitive-tier read (`can_see_unsuppressed_aggregates`) — verified visually: a line_manager sees `<5` on small demographic cells while department/level/grade breakdowns (never sensitive) stay exact
- [x] **(added)** Session-based auth (`/api/v1/auth/{csrf,login,logout,me}/`) — OIDC/Entra SSO (ADR-004) isn't built yet; this is what the SPA needs to log in against local dev/demo accounts today. `seed_demo_data` management command creates synthetic org structure + employees + three demo logins spanning hr_admin/line_manager/employee

**Bugs found and fixed during this sprint's own browser verification (not present in the Sprint 1/2 test suite, which never exercised these paths together):**
- **RBAC field-tier leak (serious):** `TieredModelSerializer` (Sprint 2) checked "does this employee hold *any* role granting this tier," not "does *that specific role* also cover this record's row-scope." Since every real employee — including managers — legitimately holds the base `employee` role (self-scope, Sensitive-tier read for their own record) alongside e.g. `line_manager`, that grant leaked onto every report's individual demographic fields, which RBAC-Roles.md reserves as aggregate-only for `line_manager`. Fixed via `can_access_tier_for_target` in `rbac_audit/permissions.py`; regression test added (`test_line_manager_who_also_holds_base_employee_role_still_cant_see_report_sensitive_fields`). The same class of bug was independently caught and fixed in the headcount dashboard's suppression check (`can_see_unsuppressed_aggregates`) before this one, via the test suite rather than the browser.
- **CSRF misconfiguration:** mutating requests 403'd in the real browser (masked by `manage.py test`'s default `enforce_csrf_checks=False`) because Django 4+ validates the browser's `Origin` header against `CSRF_TRUSTED_ORIGINS`, which wasn't set for the Vite dev origin. Added `DJANGO_CSRF_TRUSTED_ORIGINS` (settings.py + `.env.example`).
- **React anti-pattern in `LoginPage`:** a `navigate()` call in the render body (not an effect) caused erratic post-login redirects using a stale `location.state.from`. Fixed by moving the redirect into `useEffect` and dropping the "return to originally-requested page" feature in favor of always landing on `/employees` — simpler and correct.

**Exit criteria (end of Phase 1 / Core HR):** Core employee data live, RBAC/audit enforced, HR admin can manage records end-to-end. **This is the hard gate — do not start Sprint 4 until this passes UAT-lite (internal review).**

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 63/63 tests project-wide. Frontend `tsc -b && vite build` and `oxlint` both pass. All of the above additionally verified in a live Chromium session (Playwright) against the real dev servers, not just the test client — this is what surfaced the three bugs above.

---

## Sprint 4–5 — Recruitment / ATS
**Goal:** Requisition-to-hire pipeline feeding directly into `employees`.
**Status: done** (2026-08-12) — see `hcm/backend/recruitment/` (new app) and `hcm/frontend/src/pages/{Requisitions,Applicants,ApplicantDetail,RecruitmentDashboard}Page.tsx`. Verified end-to-end in a real browser as recruiter and hr_admin: create requisition → add applicant → capture consent → set demographics → move through the full pipeline → propose/approve/accept an offer → hire → confirmed the resulting `employees` row inherits the applicant's data with no re-entry.

**Tasks:**
- [x] Requisition creation and management (role, department, level, headcount) — `Requisition` model + `RequisitionViewSet`; status directly PATCHable, `opened_at`/`closed_at` auto-stamped on transition
- [x] Applicant model with pipeline stages (applied → screened → interview → offer → hired/rejected) — `Applicant.ALLOWED_TRANSITIONS` + `ApplicantStageEvent` audit trail (also what the dashboard's time-to-fill is computed from) + `recruitment/services.py::transition_applicant`
- [x] Applicant demographic capture with explicit consent flow — extended `rbac_audit.ConsentRecord` to a shared `employee`-or-`applicant` subject (Data-Dictionary.md's own documented shape, not a parallel table) rather than inventing recruitment-local consent tracking; `ApplicantSerializer.validate()` rejects writing race/gender/disability_status until `POST /applicants/{id}/consent/` has been called — enforced at the write path, not just hidden on read
- [x] Offer tracking and approval — `Offer` model + `OfferViewSet` (`approve`/`accept`/`decline` actions); `approve` enforces segregation of duties (RBAC-Roles.md standing rule 4: proposer ≠ approver), verified live in the browser (self-approve blocked with a clear error, a second user approves successfully)
- [x] Hire → automatic `employees` record creation (no re-entry) — `recruitment/services.py::_complete_hire()` calls the same `Employee.objects.hire()` Sprint 1 built for bulk import, so there's exactly one hire-to-record entry point system-wide; auto-generates the next employee number, fills the requisition (and stamps `closed_at`) once headcount is reached
- [x] Recruitment dashboard: pipeline status, time-to-fill, applicant demographics — `GET /api/v1/dashboards/recruitment/`; demographics small-cell-suppressed on the same basis as core_hr's headcount dashboard (`can_see_unsuppressed_aggregates`); demographic aggregates are consent-respecting by construction (a field can't hold a real value in the database without consent, so no extra filtering is needed at read time)

**Acceptance criteria:**
- [x] Given an applicant is marked "hired," when the record is saved, then a new `employees` row is created with no manual re-entry. — `recruitment/tests.py::HireAutomationTests`, plus live-browser confirmation (screenshot: newly hired employee's Identity + Current assignment cards match the applicant's captured data exactly)
- [x] Applicant demographic data is only visible per RBAC rules defined in Sprint 2. — consent-gated on top of (not instead of) the Sprint 2 field-tier grant; `recruitment/test_api.py::ApplicantConsentGatingTests`

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 85/85 tests project-wide (63 prior + 22 new). Frontend `tsc -b && vite build` and `oxlint` both pass. CI runs the same suite on every push.

---

## Sprint 6–7 — Performance Management
**Goal:** Goal-setting and structured review cycles tied to `employees`.
**Status: done** (2026-08-12) — see `hcm/backend/performance/` (new app) and `hcm/frontend/src/pages/{ReviewCycles,Reviews,ReviewDetail}Page.tsx` + Goals/Feedback sections added to `EmployeeDetailPage.tsx`. Verified end-to-end in a real browser: hr_admin launches a cycle → employee submits a self-review → manager submits the manager-review on the same record → manager adds a goal and feedback from the employee's detail page → hr_admin sees completion stats update live, correctly isolated per cycle.

**Tasks:**
- [x] Goal-setting model (employee + manager) — `Goal` model + `GoalViewSet`; row-scoped via the existing `RowScopePermission`/`has_row_access` (self, or your manager, or hr_admin can set a goal for you)
- [x] Configurable review cycle (annual/biannual) with launch/track/close workflow — `ReviewCycle` model; `launch_review_cycle()` snapshots every currently-active employee into a `Review` row with `manager` fixed at launch time (a mid-cycle org change can't silently reassign who's reviewing whom), idempotent by construction (unique constraint + `get_or_create`)
- [x] Manager and self-review forms — `Review` model, one row per employee per cycle; self-review and manager-review sections are independently gated (only the reviewee can write the self section, only the review's recorded manager can write the manager section) via `ReviewSerializer.validate()`, with explicit `submit_self`/`submit_manager` actions stamping the submission timestamp the completion dashboard reads
- [x] Feedback capture (manager, peer) — `Feedback` model; creation is open to any authenticated employee (peer feedback crosses the org chart by definition) but `feedback_type` is computed server-side from the org chart at write time (`classify_feedback_type`), never trusted from client input; reading is row-scoped to the subject
- [x] Review completion tracking dashboard (target: 90%+ completion visibility) — folded into the Review Cycles page itself (`GET /review-cycles/{id}/completion/`) rather than a separate page, since the acceptance criterion is "launch... and see completion status" as one flow

**A real design tension, resolved consistently with recruitment's offer-pay exception:** RBAC-Roles.md says line_manager individually "sees own team's reviews/goals," but line_manager's generic Sensitive-tier grant is closed (aggregate-only, for demographics). `Review`/`Feedback` are therefore deliberately **not** run through the generic `TieredModelSerializer` — object-level row-scope (`RowScopePermission`) is the real access gate, the same pattern already used for `recruitment.Offer`'s pay fields. `Goal` (Internal-tier, not Sensitive) has no such conflict and does use the standard tiered path.

**Bug found and fixed during this sprint's own browser verification:** the Review detail page's "Submit" button called the `submit_self`/`submit_manager` action directly without first saving the in-progress rating/comments, so a natural "pick a rating, click Submit" flow 400'd with "Set a rating before submitting" — confusing, since the rating was visibly filled in on screen. Fixed by having Submit save-then-submit in one action; "Save draft" remains available separately for saving progress without submitting.

**Acceptance criteria:**
- [x] HR admin can launch a review cycle org-wide and see live completion status. — verified live: launched a new cycle, submitted a review through the browser, watched the completion percentage change on the Review Cycles page
- [x] Performance ratings are access-restricted per RBAC (not visible to all managers by default). — row-scope-gated (self / own reporting chain / hr_admin only); `performance/test_api.py::ReviewRowScopeAndWriteGatingTests`

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 114/114 tests project-wide (85 prior + 29 new). Frontend `tsc -b && vite build` and `oxlint` both pass.

---

## Sprint 8–9 — Learning & Development
**Goal:** Skills/certifications record per employee, org-wide skills visibility.
**Status: done** (2026-08-13) — see `hcm/backend/learning/` (new app) and the Skills/Certifications/Training sections added to `EmployeeDetailPage.tsx`, plus `SkillsInventoryPage.tsx` and `TeamDevelopmentPage.tsx`. Verified end-to-end in a real browser: manager adds a skill/certification/training record to a report → HR admin views the org-wide gap-analysis dashboard → downloads a real WSP/ATR CSV export.

**Tasks:**
- [x] Skills and certification model per employee — `Skill` (Public-tier catalog, hr_admin-managed), `EmployeeSkill`, `Certification`; row-scoped writes reuse the same self/manager/hr_admin pattern as `performance.Goal` (Sprint 6)
- [x] Training record tracking (completed/in-progress) — `TrainingRecord.status` (planned/in_progress/completed/cancelled) with `hours`/`cost`, sized for WSP/ATR reporting from the start (Data-Dictionary.md: "training_record (I — feeds WSP/ATR)")
- [x] Org-wide skills inventory report (gap analysis by department/level) — `GET /dashboards/learning/skills-inventory/` (hr_admin only): per-skill holder counts broken down by department and occupational level
- [x] Manager view of team development plans — `GET /dashboards/learning/team-development/`: a per-employee skills/certifications/training rollup across whatever the requester's row-scope covers, reusing `row_scoped_queryset` rather than a bespoke access model
- [x] **(added)** WSP/ATR (SETA) export — `GET /dashboards/learning/wsp-atr-export/`, a CSV joining training data to the EEA occupational-level/demographic fields a real WSP/ATR submission needs. This was flagged as a P1 gap in `Documentation-Review-and-Gap-Analysis.md` (gap C2 — "Skills Development Act reporting... absent from L&D sprints... add WSP/ATR export to Sprints 8-9 or it will be rebuilt in spreadsheets") with this exact sprint named as the fix; not part of the original sprint plan text, added per that recommendation

**Acceptance criteria:**
- [x] Skills inventory covers imported/entered employees with no duplicate skill entries per person. — enforced by a DB-level `UniqueConstraint(employee, skill)`, not just application logic; `learning/test_api.py::test_duplicate_skill_entry_is_rejected` confirms DRF surfaces it as a clean 400, not a 500

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 134/134 tests project-wide (114 prior + 20 new). Frontend `tsc -b && vite build` and `oxlint` both pass. Along the way, extracted the `Breakdown` chart component (previously duplicated near-identically in the headcount and recruitment dashboards) into a shared `components/Breakdown.tsx` now used by all three dashboards.

---

## Sprint 10–11 — Compensation & Benefits
**Goal:** Pay bands and a controlled compensation review workflow.
**Status: done** (2026-08-13) — see `hcm/backend/compensation/` (new app) and `PayBandsPage.tsx` / `CompProposalsPage.tsx` / `BenefitsPage.tsx` in the frontend. Verified end-to-end in a real browser: comp manager defines a pay band, proposes an out-of-band raise (auto-flagged), a *different* user (hr_admin) approves it with an override reason, and a line manager/plain employee are confirmed shut out of the entire module (nav hidden, direct URL redirected, API 403).

**Tasks:**
- [x] Pay band definitions by job level (with history/versioning per Sprint 1 pattern) — `PayBand` (Restricted-tier, `valid_from`/`valid_to` + `PayBandQuerySet.as_at()/.current()`, the same effective-dated pattern as `core_hr.EmployeeVersion`); DB-level `CheckConstraint`s enforce `min ≤ mid ≤ max` and `valid_to > valid_from`
- [x] Compensation review workflow: manager proposes → approver reviews → sign-off — `CompProposal` + `compensation/services.py` (`propose_compensation_change` → `approve_proposal`/`reject_proposal`); segregation of duties enforced server-side (the proposer can't also approve — same standing rule as `recruitment.Offer.approve()`), not just hidden in the UI
- [x] Basic benefits election tracking — `Benefit` (catalog) + `BenefitsElection` (`UniqueConstraint(employee, benefit)`); recording-only this sprint, employee self-service is Sprint 15's explicit task
- [x] Pay-data visibility restricted to comp manager/HR admin roles only (strict RBAC) — `IsCompManagerOrHRAdmin` gates the *entire* module (pay bands and the benefits catalog included, not just individual salary figures), per the acceptance criterion's literal wording

**A real design tension, resolved the same way as recruitment's offer-pay exception and performance's Review/Feedback:** RBAC-Roles.md's comp_manager row-scope is "all," but comp_manager's *generic* Sensitive-tier grant is aggregate-only (S: closed) and its Restricted-tier grant is the only one in the whole role matrix with **write** access. Rather than force that mismatch through the generic `TieredModelSerializer`/`can_access_tier_for_target` path, the whole compensation module bypasses it and gates purely on role via `IsCompManagerOrHRAdmin` — plain `ModelSerializer`s throughout. `CompProposal.current_job_grade`/`status`/`requires_override` are also deliberately server-computed and marked `read_only_fields` — a client can't forge an already-approved proposal or swap the pay band it's checked against.

**Acceptance criteria:**
- [x] Compensation adjustments outside a defined pay band trigger a flag/require override approval. — `evaluate_requires_override()` checks the proposed salary against the employee's *current* pay band at propose time (missing grade or missing band is treated conservatively as requiring override, not silently waved through); `approve_proposal()` refuses to approve a flagged proposal without an `override_reason`
- [x] Pay data is not visible to line managers unless explicitly granted. — verified both ways: `compensation/test_api.py::ModuleWidePermissionTests` (API) and a live browser session (nav hidden, direct `/pay-bands` URL redirected to `/employees`)

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 166/166 tests project-wide (134 prior + 32 new). Frontend `tsc -b && vite build` and `oxlint` both pass. `seed_demo_data.py` extended with a `compmanager`/`compmanager123` demo login, pay bands per job grade (one grade carries an expired + current band to show the effective-dated pattern), and comp proposals spanning every workflow state (pending, approved in-band, approved out-of-band with an override reason, rejected).

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
