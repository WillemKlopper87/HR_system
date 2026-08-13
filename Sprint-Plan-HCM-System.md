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
**Status: done** (2026-08-13) — see `hcm/backend/assessments/` (new app), `AssessmentsPage.tsx` (employee-subject workflow), and the new Assessments section on `ApplicantDetailPage.tsx` (applicant-subject workflow). Verified end-to-end in a real browser: ee_manager assigns an employee assessment, is blocked by the consent gate, captures consent inline and retries successfully, then triggers a simulated provider completion and sees a result; a recruiter does the same against a live applicant from the recruitment pipeline; line_manager and a plain employee are confirmed shut out of the module (nav hidden, direct URL redirected).

**Tasks:**
- [x] Build internal interface: assign → redirect/embed to provider → receive results (webhook/API) → store — `assessments/adapters/base.py::AssessmentProviderAdapter` (assign/status/result), `assessments/services.py` (`assign_assessment`, `process_webhook_result`), `POST /webhooks/v1/assessments/` (HMAC-signed, versioned separately from `/api/v1/`, per Architecture-Design.md §6)
- [x] Integrate shortlisted 3rd-party provider (from Sprint 0 decision) via SSO/deep-link — **Sprint-0-Decision-Log.md action item A4 ("shortlist 1-2 assessment providers with documented APIs") remains explicitly deferred** ("not needed until Sprint 12 planning" — a procurement/vendor-evaluation task, not an engineering one). Built `assessments/adapters/sandbox.py::SandboxAdapter` instead: a real adapter implementation (not a stub) that fulfils the exact same interface a live vendor integration would, entirely in-process, so the assign → webhook → result pipeline is genuinely exercised end-to-end by tests and the demo. Swapping in a real provider once one is under contract means adding one adapter class and flipping a `ProviderConfig.active` flag (`assessments/adapters/registry.py`) — no changes to `services.py`, views, or serializers
- [x] Result ingestion into Recruitment (candidate) or L&D (employee) records — `AssessmentAssignment.employee`/`applicant_id` dual subject (see the module-boundary note below); results land against whichever subject the assignment was created for, no manual entry
- [x] Consent capture before assessment assignment — `assign_assessment()` refuses to create an assignment without an active `ConsentRecord(purpose=assessment)` for the subject, same enforcement point as recruitment's demographic-consent gate
- [x] Restrict result visibility per RBAC (treat as sensitive as demographic data) — see the permissions note below
- [ ] AI agent for assessment recommendation and plain-language result summarization — explicitly marked optional in the sprint plan ("if in scope"); out of scope for this pass (no LLM API wiring exists in this backend yet) — a candidate for a later, separately-scoped sprint

**A module-boundary design constraint, not present in earlier sprints:** `AssessmentAssignment` needs an employee-or-applicant subject — the same duality `rbac_audit.ConsentRecord` already has — but unlike `rbac_audit` (the cross-cutting layer every module may import), `assessments` is a peer domain module and Architecture-Design.md §4 draws no assessments→recruitment edge ("apps may import core_hr and rbac_audit; they may not import each other"). Importing `recruitment.Applicant` directly, even via a string FK, would violate that. `applicant_id` is therefore an **unconstrained** reference, not a cross-app FK — safe in practice since `recruitment.Applicant` rows are never hard-deleted. Consent capture follows the same boundary: `recruitment/views.py::ApplicantViewSet.consent` was generalized to accept a `purpose` field (was hardcoded to demographic_self_id) so applicant-subject assessment consent is captured through recruitment's own existing endpoint, not duplicated in `assessments`; `assessments` only ever *reads* whether consent exists (a plain `ConsentRecord` filter, no cross-module import needed for that).

**Another RBAC design tension, resolved differently from compensation's:** assessment results carry the same sensitivity as demographic data, but span two subject types with genuinely different access rules (RBAC-Roles.md: recruiter has "no access to employee performance/comp modules"; line_manager gets no assessments carve-out the way it does for reviews/goals) — too much divergence for a single row-scope model, so `TieredModelSerializer`/`can_access_tier_for_target` isn't used at all here (not even the row-scope-only bypass pattern from recruitment.Offer/performance.Review/compensation). `assessments/permissions.py::CanAccessAssessmentAssignment` gates explicitly instead: the subject employee themself, hr_admin, and auditor (read-only everywhere) can always read; ee_manager reads/writes employee-subject rows; recruiter reads/writes applicant-subject rows; line_manager gets nothing beyond their own record (no individual assessment visibility is named in RBAC-Roles.md the way "sees own team's reviews/goals" is).

**Acceptance criteria:**
- [x] Assessment results land in the correct employee/applicant record without manual entry. — the webhook handler resolves the target purely from the provider's `provider_reference` (`assessments/test_api.py::WebhookApiTests`)
- [x] Provider can be swapped by reconfiguring the integration layer, not rewriting it. — `assessments/adapters/registry.py::get_active_adapter()` resolves from the `ProviderConfig` DB row, not a hardcoded import; `AdapterRegistryTests` cover the fallback and explicit-active-row paths

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 213/213 tests project-wide (166 prior + 47 new, including full HMAC signature/replay-window coverage for the webhook endpoint). Frontend `tsc -b && vite build` and `oxlint` both pass. `seed_demo_data.py` extended with an `eemanager`/`eemanager123` demo login, a default sandbox `ProviderConfig`, and assignments spanning every state (pending employee-subject, completed employee-subject with a result, completed applicant-subject with a result against the recruitment pipeline's mid-stage candidate). Inbound webhook processing is synchronous in-request rather than a Celery task — Celery isn't wired into this codebase yet (no `tasks.py`/`celery.py` exists in any prior sprint despite the dependency being in `requirements.txt`), so introducing the first real async-task infrastructure was out of scope here; noted as a gap for whichever sprint first needs it for real, same as ADR-006's payroll sync-back being deferred to a named future sprint (12b).

*(Sprint 0 decided to integrate a 3rd-party provider (ADR-003), not build in-house, so the discovery-spike alternative below doesn't apply — but the provider shortlist itself (A4) is still open and unblocked by this sprint's completion.)*

---

## Sprint 12c — Workforce Integrity (Ghost-Employee Mitigation) — unplanned addition
**Goal:** Reduce "ghost employee" risk (people on payroll who don't actually work, or one person clocking in for several — a real fraud pattern many organisations deal with) via periodic biometric liveness verification, plus an office-attendance check against the hybrid-work policy (2 days/week in-office). Not in the original sprint plan — added mid-project at the user's request, slotted in after Sprint 12 since it reuses that sprint's just-established consent/adapter patterns most directly.
**Status: done** (2026-08-13) — see `hcm/backend/identity_verification/` (new app), `MyIdentityVerificationPage.tsx` (self-service enroll/verify, open to every employee), and `WorkforceIntegrityPage.tsx` (hr_admin's review queue + attendance dashboard). Verified end-to-end in a real browser with a **real** camera pipeline: Chromium launched with `--use-file-for-fake-video-capture` feeding an actual photo containing real faces (the `@vladmandic/face-api` package's own bundled demo/test fixture, used the same transient, non-persisted way its own maintainers use it — never committed into this repo or the seed data) so face-api.js's TinyFaceDetector + FaceRecognitionNet genuinely ran inference, not a mocked response. An employee enrolled against that real face, then re-verified moments later and got a genuine MATCH; a different employee verified against seed data's unrelated random descriptor and got a genuine NO_MATCH, correctly flagged for hr_admin review; fake geolocation set to the Johannesburg office produced `at_office: true`; hr_admin resolved a flagged review and watched it leave the pending queue; line_manager/a plain employee were confirmed unable to reach the HR review dashboard while still able to use their own self-service check-in.

**Design, addressed like a fresh ADR (see Architecture-Design.md ADR-007):**
- **No 3rd-party biometric vendor** — same reasoning as ADR-003 taken further: facial recognition has well-documented accuracy/bias problems, and this system is Employment-Equity-focused, so getting this wrong would be a real problem, not just a bug. No vendor is under contract (parallel to A4's still-open assessment-provider shortlist).
- **Client-side face descriptor extraction** (`@vladmandic/face-api`, an actively-maintained TensorFlow.js-based fork) — face detection, landmark alignment, and 128-float descriptor extraction all run in the employee's own browser. The raw photo/video frame never reaches the server; only the derived descriptor and geolocation coordinates are POSTed. Genuinely working ML inference, not a fabricated placeholder, at zero vendor cost. Code-split via `React.lazy` (the TensorFlow.js payload is ~1MB) so no other page pays for it.
- **Human review is mandatory, never automated action** — a mismatch or no-face-detected result is always queued as `review_status=pending` for hr_admin; only a human can set `confirmed_mismatch`. Nothing in this module can, by itself, flag someone as a confirmed ghost employee.
- **POPIA**: biometric data is "special personal information" (s26/27) — gated by its own dedicated `ConsentRecord.Purpose.BIOMETRIC`, distinct from this system's ordinary consent flows, checked before both enrollment and every check-in.
- **Module-boundary consistency**: `identity_verification` only imports `core_hr`, matching every other module's constraint — no new exception needed here (unlike `assessments`, it has no cross-subject-type problem to solve).
- **Office-attendance policy (2 days/week)**: computed via Haversine distance from device geolocation to the employee's assigned `core_hr.Location` (extended with optional `latitude`/`longitude` — a geofence must be configured per site; ungeofenced locations correctly report "unknown," not "absent"). The 200m geofence radius and the 2-day/week threshold are documented constants in `identity_verification/geo.py`, explicitly awaiting a real home once the policy-document sprint below exists.

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 253/253 tests project-wide (213 prior + 40 new). Frontend `tsc -b && vite build` and `oxlint` both pass. `seed_demo_data.py` extended with real office coordinates for all four seeded locations and a spread of enrollments/check-in history (including one check deliberately left pending review, so the hr_admin queue isn't empty on a fresh demo).

**Queued next (explicitly out of scope for this addition):** the user also asked for a **Policy section** — an HR policy document library with (likely) per-employee acknowledgment tracking, which the attendance/geofence constants above should eventually move into. Not started; the next unplanned addition once Sprint 13–14 or this one's follow-ups are through.

---

## Sprint 13–14 — Equity / EE Reporting
**Goal:** Draft EEA2/EEA4 generation using data now enriched by Recruitment, Performance, Compensation.
**Status: done** (2026-08-13) — see `hcm/backend/ee_reporting/` (new app), `EEConfigurationPage.tsx` (Section A employer identity + questionnaire + remuneration CSV import), `EEReportsPage.tsx` (generate/submit/review/sign-off/export), and `EquityDashboardPage.tsx` (live target-vs-actual tracking). Field layouts and category lists (24 barrier categories, 7 justifiable reasons, 3 consultation stakeholders, 8 differential reasons, 6 business types) were extracted **verbatim** from the actual `EEA2 Form.docx`/`EEA4 Form.docx` source files (via a one-off zipfile+regex extraction, since neither is readable directly), not paraphrased from the notes doc, into a single shared `ee_reporting/constants.py` — a real annual Department of Employment and Labour wording change is a one-file edit, not a hunt across models/aggregation/export/frontend.

**Tasks:**
- [x] Validation engine: check report readiness against required fields — `ee_reporting/validation.py::validate_report_readiness()`: employer config completeness, a questionnaire for the report year, remuneration data for the period (EEA4), plus a genuine **cross-form rule**: EEA4 headcounts must exactly match the current EEA2's Section B grand total per demographic column, or generation is blocked with the specific mismatched columns named
- [x] Draft EEA2-style report generation — `services.py::generate_report(form_type="eea2", ...)`; workforce profile, disability workforce, recruitment/promotion/termination movement, and skills-development matrices, all computed live from `core_hr`/`learning` at generation time
- [x] Draft EEA4-style report generation — headcount + total-remuneration matrices, highest/lowest-paid-by-level, and median/gap statistics (top-5%/bottom-5% split, vertical gap multiple)
- [x] Export to PDF/Excel/CSV/XML per official spec — `export.py` (openpyxl, reportlab, stdlib `xml.etree`/`csv`); spec-data-aligned exports (every field and matrix cell the form requires), not pixel-perfect form replicas
- [x] Approval workflow: draft → HR review → EE manager review → sign-off → archive — `EEReport.Status`: `draft → pending_ee_review → pending_signoff → signed_off`, with prior non-signed-off versions of the same form+year auto-marked `superseded` on regeneration (the "frozen snapshot" pattern from Architecture-Design.md §5.1 — a later data correction never silently changes an already-generated report)
- [x] Full equity dashboard (department, level, pay band, race, gender, disability) — `dashboards.py::equity_dashboard` extends Sprint 3's headcount dashboard with the same level x population-group x gender matrix EEA2 Section B uses, live rather than a frozen snapshot, with the same small-cell (n<5) suppression rule
- [x] EE target-vs-actual tracking — `EEPlan.annual_targets` (a target % per level x demographic column) vs. the live workforce matrix, reported as a percentage-point gap per cell

**A new RBAC role, gated deliberately narrowly:** PFMA requires the Accounting Officer (in practice, the CEO) to personally sign off EEA2/EEA4 — a real person distinct from hr_admin/ee_manager. Added `accounting_officer` (`rbac_audit/migrations/0005_seed_accounting_officer_role.py`, `row_scope=all`, **no** generic P/I/S/R field-tier grants — mirrors `sysadmin`'s "no standing access to business data" precedent). This means accounting_officer has full access to actual generated reports (via `EEReportingPermission`'s explicit role check) but is correctly **still subject to small-cell suppression on the live Equity Dashboard**, since that dashboard's suppression check (`can_see_unsuppressed_aggregates`) requires an explicit sensitive-tier grant that this role was intentionally never given — verified live in the browser, not just asserted; confirms the sign-off duty (exact legal figures in the frozen document) and casual org-wide browsing (privacy-protected live aggregates) are correctly two different bars.

**Two real bugs found and fixed by this sprint's own tests (both would have shipped invisibly without them):**
- **Permission-class over-blocking:** `EEReportingPermission` initially restricted every write action to `hr_admin` only, at the DRF permission-check layer that runs *before* a view method's own body. This silently 403'd `ee_manager`'s `ee_review` action and `accounting_officer`'s `sign_off` action even though each already had its own correct, specific `has_role()` check inside the view — the outer gate never let the request reach that check. Caught by `test_ee_manager_can_perform_ee_review_step` / `test_accounting_officer_can_sign_off`. Fixed by broadening the permission class to a coarse "any EE-reporting role" gate and moving the truly hr_admin-only restrictions into an explicit `_require_hr_admin()` check inside the specific view methods that need it — same "broad gate + fine-grained in-view checks" shape as `assessments.CanAccessAssessmentAssignment`.
- **`?format=` query-param collision:** the export action originally read `?format=csv|xlsx|pdf|xml`, not realising `format` is DRF's own reserved query parameter for response-renderer content negotiation (`URL_FORMAT_OVERRIDE`) — every export request 404'd *before* the view method ever ran, from deep inside `perform_content_negotiation()`, which looked exactly like a broken object lookup until a `handle_exception` traceback dump exposed the real `Http404` origin in `rest_framework/negotiation.py`. Renamed to `export_format` everywhere (backend, tests, frontend).
- A third bug surfaced only in the browser, not by any Django test: `EEConfigurationPage.tsx`'s employer-config and questionnaire forms are pre-fill/edit forms fed by an async fetch, but seeded their `useState` from the `config`/`questionnaire` prop *once, at mount* — since both start `null` before the fetch resolves, the forms permanently locked onto blank defaults and never picked up the real fetched data. Saving without touching every field would have silently overwritten real Section A/questionnaire data with empty strings. Fixed with the same prop-resync `useEffect` pattern `ReviewDetailPage.tsx`'s rating/comments editor already uses. A reminder that `manage.py test` passing said nothing about this — only opening the actual page and reading the actual input values caught it.

**Acceptance criteria:**
- [x] Generated draft report matches official EEA field layout. — field/category lists extracted verbatim from the source `.docx` forms (see Goal above), asserted in `ConstantsTests` (e.g. `assert len(BARRIER_CATEGORIES) == 24`)
- [x] Every generated report is versioned and archived with sign-off record. — `EEReport.version` + `Status.SUPERSEDED` on regeneration; `signed_off_by`/`signed_off_at`/`signed_off_place` captured on sign-off, covered by `ApprovalWorkflowTests`

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 315/315 tests project-wide (253 prior + 62 new: 41 `ee_reporting/tests.py` + 21 `ee_reporting/test_api.py`). Frontend `tsc -b && vite build` and `oxlint` both pass. `seed_demo_data.py` extended with a realistic `EmployerConfig`, current-year `EEQuestionnaire`, a 2025–2030 `EEPlan`, pay-band-scaled (not flat) remuneration for every employee, and one EEA2 walked all the way to `signed_off` while its EEA4 sibling is left in `draft` — so the demo has both a finished report to inspect and an actionable one to progress. Verified end-to-end in a real browser across four roles: hr_admin generated/exported/reviewed reports and confirmed the cross-form validation message names the exact mismatched columns; ee_manager could approve but not submit-for-review or reach Workforce Integrity; accounting_officer saw suppressed live-dashboard aggregates but unrestricted signed-report data; line_manager was confirmed redirected away from all three new routes on direct URL access, with no nav links shown. All four export formats (CSV/Excel/PDF/XML) downloaded real non-empty content through the actual running app, not just asserted at the API layer.

**Queued next (still explicitly out of scope):** the Policy section (HR policy document library + acknowledgment tracking) requested alongside Sprint 12c remains not started — see the dedicated Policy section entry below (added after Sprint 15).

---

## Sprint 15 — Employee Self-Service
**Goal:** Employees manage their own profile/consent/benefits/learning requests.
**Status: done** (2026-08-13) — see `MyProfilePage.tsx`, `MyBenefitsPage.tsx`, `MyLearningPage.tsx` (all three routed like `MyIdentityVerificationPage` — open to every authenticated employee, unrouted from `RequireRole`, self-scoped entirely server-side rather than through a different URL). No new backend app: every change reuses and extends `core_hr`/`compensation`/`learning`'s existing endpoints, since ESS is "the same records, a narrower lens," not a new domain.

**Tasks:**
- [x] Self-ID submission flow with consent tracking — `EmployeeViewSet.consent`/`self_identify` actions (`core_hr/views.py`), mirroring `recruitment.ApplicantViewSet`'s consent-then-write shape exactly: `self_identify` 400s with a pointer to `POST /employees/{id}/consent/` until an active `ConsentRecord(purpose=demographic_self_id)` exists, then updates the *current* `EmployeeVersion`'s race/gender/disability fields in place (not a new version+lifecycle event — self-ID is a classification correction, not an employment fact, and none of `EmploymentEvent.EventType`'s fixed choices fit), stamping `race_source`/`disability_source = SELF_IDENTIFIED`. `EmployeeSerializer.has_demographic_consent` mirrors `ApplicantSerializer`'s own field so the frontend never needs a separate lookup.
- [x] Profile update UI (employee-editable fields only) — `EmployeeViewSet` is now a `ModelViewSet` (was read-only through Sprint 3-14), restricted to `http_method_names = ["get", "post", "patch", "head", "options"]` with `create()` explicitly overridden to 405 (generic employee creation still only happens via `hire()`/recruitment) — POST stays open only for the two actions above, since DRF's router gates action routes through the same method allowlist as `create()`. `EmployeeSerializer.validate()` is the real write gate: self or hr_admin only, and only `{preferred_name, personal_email, phone}` — RowScopePermission's row-scope check alone would have let any all/own_team-scope role (auditor, line_manager) reach PATCH too, which is far too broad for a write.
- [x] Benefits election self-service — `BenefitViewSet` switched to read-open (`IsCompManagerOrHRAdminOrReadOnly`, same shape as `core_hr.IsHRAdminOrReadOnly`) so employees can browse the catalog; `BenefitsElectionViewSet` switched to `IsSelfOrCompManagerOrHRAdmin` (object-level self-or-privileged, same shape as `identity_verification.IsSelfOrHRAdmin`) with `get_queryset()` row-scoping the list to the caller's own elections and `perform_create()` force-setting `employee=requester` for non-privileged callers regardless of what the client sent — comp_manager/hr_admin keep full access, unchanged from Sprint 10-11.
- [x] Learning enrollment requests — added `TrainingRecord.Status.REQUESTED`; `TrainingRecordSerializer.validate()` forces a self-submission's status to `REQUESTED` and strips `hours`/`cost`/`completion_date` regardless of client input on create, and blocks a self-submitter from later editing `status`/`hours`/`cost`/`completion_date` on their own pending request (title/provider/start_date remain self-editable) — only someone else with row access (manager/hr_admin) can move it past `REQUESTED`. Deliberately no self-approval carve-out for privileged roles either: the distinguishing check is requester-vs-target identity, not role, so even hr_admin's own self-submitted training request is forced to `REQUESTED`.

**A write-authorization gap RowScopePermission alone doesn't close, worth naming explicitly:** every prior sprint's use of `RowScopePermission` was for *reads* (or writes already narrowed by a dedicated permission class, e.g. `assessments.CanAccessAssessmentAssignment`). Opening `EmployeeViewSet` to PATCH is this sprint's first case of layering a real write onto the generic row-scope check without a bespoke permission class — and row-scope coverage (who can *see* a record) is a materially wider set than who should be able to *write* to it (auditor and any all-scope role reads everyone; only self/hr_admin should write here). `EmployeeSerializer.validate()` is where that authorization actually lives, not the permission class — worth remembering for any future module that adds writes to an already-read-only, row-scoped endpoint.

**Acceptance criteria:**
- [x] An employee can update their own contact details and submit demographic self-ID with consent captured. — `EmployeeSelfServiceApiTests` (core_hr) + browser-verified live
- [x] An employee cannot write fields outside the ESS-editable set, or act on another employee's record. — same test class; `test_employee_cannot_update_identity_fields`, `test_employee_cannot_update_someone_elses_profile`, `test_employee_cannot_self_identify_for_someone_else`
- [x] An employee can elect/waive their own benefits without seeing or affecting anyone else's. — `BenefitsSelfServiceApiTests` (compensation)
- [x] A learning enrollment request starts in a distinct "requested" state and only a manager/HR can move it forward. — `TrainingRecordEnrollmentRequestApiTests` (learning)

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 332/332 tests project-wide (315 prior + 17 new). Frontend `tsc -b && vite build` and `oxlint` both pass. `seed_demo_data.py` extended with a deliberately light-touch `_seed_ess_demo_data`: the `employee` demo login's own contact details and self-ID are left untouched (empty/not-consented) so a live demo has something real to fill in rather than just confirming already-seeded data renders, while one `REQUESTED` training record and a guaranteed benefits election keep My Learning/My Benefits from looking empty on first login. Verified end-to-end in a real browser: logged in as `employee`, updated contact details, captured self-ID consent, submitted self-identification and confirmed it persisted after a reload, waived and could re-elect a benefit live, and submitted a new enrollment request that was correctly forced to `Requested`; logged in as `manager` and confirmed a real authenticated PATCH could approve the report's request (`requested` → `planned`) while a self-submitted request for the manager's own training was equally forced to `Requested` (no self-approval loophole); confirmed a third employee (`recruiter`) sees the same self-service nav links and only ever their own profile, not gated by role the way every other module's nav is.

---

## Policy Section — HR Policy Library & Acknowledgment Tracking (unplanned addition, ADR-008)
**Goal:** An HR policy document library with per-employee acknowledgment tracking. Requested alongside Sprint 12c (2026-08-13), deliberately deferred out of that sprint's scope, picked up here as its own unit of work after Sprint 15.
**Status: done** (2026-08-13) — see `hcm/backend/policies/` (new app), `PolicyLibraryPage.tsx` (hr_admin CRUD + publish/archive/new-version workflow + document upload), `MyPoliciesPage.tsx` (every employee — read + acknowledge, unrouted from `RequireRole` like `MyIdentityVerificationPage`), and `PolicyComplianceDashboardPage.tsx` (hr_admin — per-policy acknowledgment completion %).

**Tasks:**
- [x] Policy document library with versioning — `Policy` model: `code` is the stable identity shared across every version (same pattern as `ee_reporting.EEReport`'s `form_type`+`report_year`), `version` is server-computed, `status` runs `draft → published → archived`; publishing auto-archives whichever version was previously published under the same code (`services.py::publish_policy`). Never edited in place once published — a correction is a new draft version, so an acknowledgment always points at an exact, immutable version.
- [x] Per-employee acknowledgment tracking — `PolicyAcknowledgment` model, idempotent `acknowledge_policy()` (re-acknowledging the same version is a no-op, not an error), always self-recorded even for hr_admin (no "acknowledge on someone's behalf" path — unlike `compensation.BenefitsElection`, an attestation only means something as your own act).
- [x] Acknowledgment compliance dashboard — `dashboards.py::acknowledgment_dashboard`: per currently-published policy, acknowledged count / active workforce size / completion %, hr_admin-only.

**Requested mid-build (2026-08-13), scoped in phases (ADR-008):** the user asked for uploaded PDF/other documents to be read, processed, and eventually made queryable by a chatbot/LLM, with an explicit ask to plan for users trying to prompt a future chatbot into revealing how to circumvent or find loopholes in a policy. Given the choice of how far to build this now, the user picked **"upload + extraction + chunking seam"** — real, tested plumbing with no LLM calls:
- [x] Document upload + text extraction — `Policy.source_file` (FileField, local disk for dev/pilot scale — ADR-005-style deferral to S3/Azure Blob for real production, same pattern as everywhere else a real vendor is a later decision) alongside the extracted `body` text. `policies/extraction.py` supports PDF (`pypdf`), DOCX (`python-docx`), and TXT/MD; a scanned/image-only PDF (no extractable text) is rejected at creation time rather than silently publishing a blank policy — no OCR.
- [x] Deterministic chunking pipeline — `policies/chunking.py::chunk_text()`: paragraph-aware, sentence-boundary fallback for an over-long paragraph, no ML/embedding dependency (~1000 chars ≈ a 250-token passage, a common rule-of-thumb chosen without committing to any specific model's real tokenizer, since none has been picked yet). `PolicyChunk` rows are server-recomputed (never client-writable) whenever a draft's body changes, and are inspectable via `GET /policies/{id}/chunks/` — the concrete data plumbing a future retrieval phase would embed and search over.
- [ ] Embeddings + vector search/retrieval — **explicitly deferred**, not built. No vector store or embedding model exists in this codebase.
- [ ] The chatbot itself — **explicitly deferred**, not built. No LLM API integration exists anywhere in this codebase yet (confirmed again during this sprint — same as when Sprint 12's optional AI summarization task was scoped out); wiring one is a real per-query cost and vendor decision needing explicit sign-off, not something to bolt on incidentally.
- [ ] Abuse-prevention design for circumvention-framed questions — **planned, not implemented** (there's no chatbot yet to guard). The design requirement, recorded here and in `Architecture-Design.md` ADR-008 so it isn't lost before the chatbot phase starts: retrieval-augmented answers must stay strictly grounded in a policy's own chunked text (never general knowledge or invented exceptions), the system prompt must refuse circumvention/loophole-framed questions rather than answer them, and every Q&A turn must be logged for HR audit — the same "no automated adverse action without a human in the loop" posture ADR-007 established for biometric mismatches, applied here to policy advice instead of enrollment decisions.

**Acceptance criteria:**
- [x] HR can publish a policy (typed or uploaded) and employees can read and acknowledge the exact published version. — `PolicyWorkflowApiTests`, `PolicyAcknowledgmentApiTests`, browser-verified live end to end including a real PDF upload
- [x] A policy correction never silently changes what an employee already acknowledged. — `test_acknowledgment_is_pinned_to_the_specific_version`; publishing v2 archives v1 but existing v1 acknowledgments remain unchanged and don't carry forward
- [x] hr_admin can see acknowledgment completion per policy. — `PolicyAcknowledgmentDashboardApiTests`, browser-verified

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 379/379 tests project-wide (332 prior + 47 new: `policies/tests.py` + `policies/test_api.py`, covering the workflow, chunking, and real PDF/DOCX/TXT extraction — reportlab-generated PDFs and python-docx-generated DOCX files round-tripped through the actual extractor, not fixtures). Frontend `tsc -b && vite build` and `oxlint` both pass. `seed_demo_data.py` extended with three published policies at varied acknowledgment completion (0%, ~40%, ~66% — not 0% or 100% everywhere) — one of them created from a genuinely uploaded text file to exercise extraction in the seed script too — plus one policy left in `draft` for hr_admin's live publish demo; the `employee` login has acknowledged one policy and left another outstanding on purpose. Verified end-to-end in a real browser: hr_admin published the seeded draft live, uploaded a real reportlab-generated PDF through the actual upload UI and confirmed the exact extracted sentence appeared in the draft's body textarea (not asserted at the API layer only), and the uploaded document round-tripped through a real HTTP download afterward; employee acknowledged an outstanding policy live and the compliance dashboard's percentage updated to match; a plain employee and a different employee (recruiter) both confirmed self-scoped to My Policies with the hr_admin-only Policy Library/Compliance nav links correctly hidden.

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
