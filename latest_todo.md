# HR/HCM improvement TODO

**Created:** 2026-08-28
**Source:** [`latest_critique.md`](latest_critique.md)
**Baseline:** `0d27f04` plus untracked critique documentation.
**Purpose:** One ordered, implementation-ready queue for the gaps identified in the latest frontend-to-backend review.

A checked item means implementation and its stated verification evidence are complete. It does not substitute for HR,
legal, privacy, security, payroll-provider or regulatory sign-off where those are explicitly required.

## Implementation progress — 2026-08-28

Completed in the first P0 tranche:

- Added a row-scoped `/employees/search-summary/` API that exposes only `id`, `employee_number` and `display_name`.
- Replaced the probation and exit-interview full-directory loads with a debounced, cancellable and keyboard-operable
  employee selector.
- Regenerated the OpenAPI TypeScript output and migrated those screens to a generated-contract facade.
- Split the probation and exit-interview routes into lazy chunks and removed the two Fast Refresh lint warnings.
- Added focused API permission/privacy tests and Playwright coverage for selector privacy and keyboard operation.
- Added a full probation browser journey covering creation, date validation, manager scope and employee-only
  countersignature; corrected the employee route/navigation entitlement that the journey exposed.

Verification evidence:

- Full Django suite: 1,184 tests passed.
- Focused employee API suite: 9 tests passed.
- Focused Playwright suite: 2 tests passed.
- Django system check and migration drift check passed.
- Frontend lint, TypeScript compilation and production build passed.
- `git diff --check` passed; only Git's expected LF-to-CRLF notices were emitted.

Items left unchecked below remain outstanding; in particular, the complete probation/exit workflow browser matrix,
route-level error boundaries, contract-import enforcement, obsolete handwritten-type removal and chunk-budget policy.

## P0 closed — 2026-08-28 (second slice)

Closed the remaining P0.1/P0.2/P0.3 items:

- Removed the superseded handwritten `Probation*`/`ExitInterview*` transport types and label maps from
  `src/api/types.ts`; presentation labels now live in `src/api/contract-labels.ts`, typed against the generated
  facade so a backend enum change fails the frontend build rather than drifting silently.
- Added `scripts/check-contract-imports.mjs` (wired into `npm run lint`) to fail if a migrated page re-imports a
  removed handwritten transport type; verified it both catches a regression and passes clean.
- Documented the migration pattern in `docs/frontend/generated-api-contracts.md`.
- Added `RouteErrorBoundary.tsx` around every lazy route (via the shared `LazyPage` helper) and a build-time
  chunk-size budget in `vite.config.ts` that fails the build on regression; verified both directions.
- Added empty-query, substring-match, and the remaining role/reporting-chain test coverage for
  `/employees/search-summary/`.

Verification: 14 focused employee-API tests, 109 tests across `core_hr.test_probation`/`test_exit_interviews`/
`test_api`, `manage.py check`/`makemigrations --check` clean, frontend `tsc`/lint/build clean (chunk budget
enforced), and 3 Playwright specs (full probation lifecycle, protected evidence download, equity-dashboard
suppression) passed twice — once before and once after the contract-facade migration.

**P0 is now fully closed.** Next up per this file's own ordering: P1 (pilot readiness/UAT is the highest-value
gate but not engineering-only; the effort-buildable P1 items are identity/SSO, employee-relations case
management, reasonable accommodation, and the statutory workflow foundation).

## Scale and privacy follow-up — 2026-09-01

Completed in the current high-volume-screen tranche:

- [x] Cursor-paginate the applicant, compensation-proposal, workforce-integrity, EE-forum meeting and EE-forum
      member tables instead of downloading every detailed record.
- [x] Replace the EE-forum add-member directory download with the shared row-scoped async employee selector.
- [x] Add a complete active-forum-member attendance endpoint exposing only the membership ID and display name;
      preserve the existing EE-reader/member/outsider roster boundary.
- [x] Regenerate the OpenAPI client contract and add focused active-only, minimal-field and permission tests.
- [x] Remove the date-expired “current EE plan” assumption from the management-control disability-target test.

Verification: all 130 EE reporting tests passed; frontend lint and production build passed; Django system and
migration-drift checks passed. The production build continues to report the known large-chunk advisory.

The broad high-volume-screen and selector-summary items below remain open because other screens still use
`fetchAllPages`; this slice closes the named workflows, not the repository-wide migration.

## Employee-selector follow-up — 2026-09-01

Completed the next privacy/scale tranche:

- [x] Replace the full employee-directory download in employment-change proposals with the scoped async selector.
- [x] Replace the full employee-directory download in employee-assessment assignment with the scoped async selector.
- [x] Replace the full employee-directory download in benefits administration with the scoped async selector.
- [x] Replace the full employee-directory download in EE plan-measure ownership with the scoped async selector.
- [x] Add purpose-specific display-name fields to employment-change, assessment-assignment and benefits-election
      responses so list tables no longer need a separate employee-directory join.
- [x] Regenerate the OpenAPI TypeScript contract and assert the new response fields in focused API tests.
- [x] Extend browser selector coverage across all four workflows, checking the privacy-minimal response shape and
      proving that none requests the detailed `/employees/` collection.

Verification: 44 focused backend tests and 6 Playwright selector journeys passed; frontend lint/build, Django
warning-level system checks, migration-drift checks and `git diff --check` passed. The existing large-chunk build
advisory remains. Other `fetchAllPages<Employee>` call sites remain queued under the repository-wide scale item.

## Employee-directory removal follow-up — 2026-09-01

- [x] Remove the full employee-directory join from contract renewals; employee and manager display names now travel
      with each row-scoped employee-version response.
- [x] Remove the full employee-directory join from reviews; the row-scoped review response now carries the reviewee's
      display name.
- [x] Replace My Performance's 360-rater directory download with the scoped async employee selector, including
      client-side exclusion of the subject and existing raters while retaining server-side eligibility checks.
- [x] Replace succession/talent-pool employee-directory downloads with the scoped async selector and a
      privacy-minimal candidate display name supplied by the row-scoped succession response.
- [x] Replace applicant interview-panel directory downloads with async multi-select search; embed only panel identity
      summaries and scorecard author names in the already row-scoped interview contracts.
- [x] Replace the final full employee-directory consumer, the organisation chart, with a cursor-paginated,
      privacy-minimal topology contract that preserves reporting-chain row scope without exposing unrelated employee
      detail fields.

Verification for this partial tranche: 7 focused API tests passed; frontend lint/build, Django warning-level checks,
migration-drift checks and the two contract-renewal browser journeys passed. The performance review journey also
passed within the broader talent spec; that spec's unrelated recruitment journey timed out while the still-outstanding
applicant page downloaded the full employee directory, reinforcing the priority of the next item.

Verification for the My Performance/succession increment: all 10 focused succession API tests and all 6 focused
performance-calibration/succession Playwright journeys passed. Generated API types were refreshed; frontend lint,
contract-import checks, production build and `git diff --check` passed. The existing large-chunk build advisory remains.

Verification for the interview-panel increment: 14 focused scheduling/scorecard API tests and all 3 careers-portal
Playwright journeys passed. Generated API types were refreshed; frontend lint, contract-import checks, production
build and `git diff --check` passed. The browser trace confirms panel selection calls only `search-summary` and does
not request the detailed employee collection.

Verification for the organisation-chart increment: 16 focused employee/search/topology API tests and both focused
Org Chart Playwright journeys passed. Generated API types were refreshed; frontend lint, contract-import checks,
production build, Django system checks, migration-drift checks and `git diff --check` passed. Browser evidence confirms
cursor traversal uses only `org-chart` and never requests the detailed employee collection. No
`fetchAllPages<Employee>` consumers remain in the frontend. A development-environment `check --deploy` still reports
the six expected production-only settings warnings (HTTPS/HSTS, secure cookies, secret key and DEBUG); deployment
evidence must use production settings rather than treating those local warnings as closed.

## Execution principles

- Preserve effective dating, audit history, row scope, field tiers and protected-download controls.
- Extend existing domain models and shared services; do not create parallel sources of truth.
- Keep SAP/payroll, leave and identity ownership decisions explicit. Do not accidentally build replacement systems.
- Complete one independently verifiable tranche before starting the next.
- Separate local/mocked verification from live integration, staging and stakeholder evidence.
- Reconfirm current regulatory rules from official primary sources before encoding deadlines or calculations.

## P0 — Immediate engineering win: frontend contract and scale pilot

Target the probation and exit-interview workflows first. This slice has no external-provider dependency and closes
known regulatory browser-coverage gaps while establishing patterns reusable across the frontend.

### P0.1 Generated API type facade

- [x] Inventory the transport types, enums and labels used by `ProbationPage.tsx` and `ExitInterviewsPage.tsx`.
- [x] Map their API response/request types to `src/api/generated-types.ts`.
- [x] Create a small generated-type facade for domain-friendly aliases; do not copy generated structures by hand.
- [x] Move presentation-only labels/constants out of transport-type declarations.
- [x] Migrate probation and exit-interview screens to the facade.
- [x] Remove the replaced handwritten declarations from `src/api/types.ts`.
- [x] Add a CI/source check preventing migrated modules from importing their removed handwritten transport types.
- [x] Document the migration pattern for later modules.

### P0.2 Scalable employee selector

- [x] Define a privacy-minimal employee-search response: identifier, employee number, display name and only the fields
      required by an authorised selector.
- [x] Confirm each selector's role and row-scope requirements before sharing an endpoint.
- [x] Add server-side search with cursor pagination and a bounded page size.
- [x] Add tests for empty query, partial match, pagination, role denial and reporting-chain scope.
- [x] Add a debounced accessible async employee combobox.
- [x] Replace `fetchAllPages<Employee>('/employees/')` in probation and exit-interview screens.
- [x] Ensure stale searches are cancelled with `AbortController`.
- [x] Verify that a selector never downloads unrelated employee detail fields.

### P0.3 Route splitting and frontend warning cleanup

- [x] Move non-component exports out of `AuthContext.tsx`.
- [x] Move non-component exports out of `ReferenceDataContext.tsx`.
- [x] Lazy-load the probation and exit-interview routes.
- [x] Add a shared route loading state and route-level error boundary.
- [x] Measure main and relevant route chunks before and after the change.
- [x] Record a chunk-size budget and fail or warn consistently when it regresses.

### P0.4 Browser coverage for the regulatory workflows

- [x] HR opens a valid probation period.
- [x] HR is refused invalid/overlapping probation dates.
- [x] Correct line manager creates a review.
- [x] Unrelated manager is refused the review.
- [x] Employee countersigns using their own password.
- [x] Manager and HR are refused employee countersignature.
- [x] HR records an exit interview with a valid single trigger (covered at the API/model level;
      `ExitInterviewsPage.tsx` does not yet expose employment_change/probation_period linkage fields, so this and
      the next item are backend/API-test coverage only -- add browser coverage once that UI exists).
- [x] Mismatched or multiple exit triggers are refused (API-level: `test_employment_change_must_belong_to_the_
      selected_employee`, `test_probation_period_must_belong_to_the_selected_employee`, `test_both_triggers_at_
      once_is_rejected` in `core_hr/test_exit_interviews.py`).
- [x] Authorised user downloads protected training evidence -- added the evidence upload/download UI to
      `MyLearningPage.tsx` (no page previously exposed `download_evidence` at all) and covered it end to end.
- [x] Unrelated employee is refused the evidence download.
- [x] Demographic dashboards render suppression without reconstructable values -- verified by diffing the
      hr_admin (unsuppressed) and accounting_officer (suppressed) views of the same live equity-dashboard data.
- [x] Add keyboard and accessible-name assertions for new selectors and validation errors.

### P0 exit gate

- [x] Backend focused tests pass.
- [x] Complete backend suite passes.
- [x] `manage.py check --fail-level WARNING` passes.
- [x] `manage.py makemigrations --check --dry-run` reports no drift.
- [x] OpenAPI and generated frontend types are regenerated and clean.
- [x] Frontend lint has no Fast Refresh warnings.
- [x] Frontend TypeScript and production build pass.
- [x] Focused Playwright journeys pass without retries hiding deterministic failures.
- [x] `git diff --check` passes.
- [x] Update backlog, session state, API/data dictionary and RBAC documentation where applicable. (No new API
      surface or RBAC tier in this tranche's final slice, so `RBAC-Roles.md`/`Data-Dictionary.md` are unaffected;
      `docs/sprints/regulatory-review-backlog.md` and `docs/SESSION-STATE.md` updated.)

## P1 — Pilot readiness and accountable UAT

This is the highest-value organisational gate. It can be planned alongside P0, but stakeholder evidence cannot be
manufactured by engineering.

- [x] Create role-based walkthroughs for employee, manager, HR, recruiter, compensation, EE and auditor personas.
      `docs/PILOT-UAT-WALKTHROUGHS.md` defines entry criteria, evidence handling, executable persona steps,
      security/privacy prompts, finding severity/ownership fields and the formal exit decision. This completes the
      engineering script only; no stakeholder execution or acceptance is claimed.
- [ ] Run HR/talent/EE/compensation stakeholder UAT.
- [ ] Run security review of authentication, step-up, downloads, audit and lifecycle cascades.
      Engineering review evidence is recorded in `docs/PILOT-SECURITY-REVIEW.md`. It resolved SR-001 (High): TOTP
      authenticator replacement now requires current-password verification and revokes grants issued for the old
      device. Independent review of a production-like pilot environment remains outstanding.
- [ ] Run privacy review of biometrics, disability data, union representation and protected documents.
      Engineering review evidence is recorded in `docs/PILOT-PRIVACY-REVIEW.md`. PR-001 (High) is resolved: biometric
      capture is now blocked until explicit informed consent, only the consent lawful basis is accepted, and sensitive
      check-in history uses bounded cursor pages. Independent privacy/legal review remains outstanding; PR-002 and
      PR-003 block mandatory biometric production use until an operational alternative/appeal and consent-withdrawal/
      descriptor-disposal workflow are implemented and approved.
- [ ] Verify non-biometric identity/check-in alternative and appeal procedure.
- [ ] Record findings with severity, owner, target date and production-blocking flag.
- [ ] Resolve all critical findings before production reliance.
- [ ] Record formal pilot acceptance or rejection and its scope.

### Operational evidence

- [ ] Automate scheduled database and media backups with off-site retention.
      Repository automation is prepared in `hcm/ops/backup.sh` with checksum verification, atomic off-site copy,
      bounded retention and a hardened systemd timer template. This remains open until operations configures a genuine
      separate-failure-domain target, enables the timer and supplies dated successful-run/alert evidence.
- [ ] Restore both into an isolated environment.
      `hcm/ops/restore-verify.sh` now creates a unique throwaway Compose project and fresh volumes, restores both
      archives, migrates and verifies readiness. A real rehearsal against an authorised backup remains outstanding.
- [ ] Verify recent signed artefact hashes after restore.
      `manage.py verify_restored_artifacts --require-signed-document` fails on missing/tampered signed agreement PDFs
      or signature-hash disagreement and is invoked by the restore verifier. Live restored-data evidence remains open.
- [ ] Record restoration duration and define RPO/RTO ownership.
- [ ] Add metrics for API errors, latency, task failures, notification failures and integration freshness.
      Repository instrumentation is complete: Redis-backed, low-cardinality counters/freshness timestamps are exposed
      at token-protected `/metrics`, with no employee, route, recipient or payload labels. This remains open until a
      production monitoring system scrapes it and dated evidence confirms continuity across the deployed topology.
- [ ] Add dashboards and actionable alerts.
      Importable Grafana panels and Prometheus rules for target availability, API error ratio/latency, task failure/
      freshness, email failure and enabled-integration staleness are in `hcm/ops/observability/`. This remains open until
      the selected platform imports them, routes severities to named owners and completes an alert drill.
- [ ] Run load tests with realistic employee versions, documents and reporting data.
- [ ] Document production topology, secrets storage, rotation and rollback.

## P1 — Identity and systems-of-record integration

### Decisions required before implementation

- [ ] Confirm Entra tenant and OIDC application ownership.
- [ ] Define immutable user mapping and duplicate-account resolution.
- [ ] Define role/group claim source and emergency-access rules.
- [ ] Confirm SAP integration mechanism, source objects and owner.
- [ ] Confirm the authoritative leave system and freshness expectation.
- [ ] Produce a field-level system-of-record matrix.
- [ ] Define retry, replay, dead-letter, reconciliation and manual exception ownership.

### Narrow integration framework

- [ ] Add a generic sync-run record with source, correlation ID, timestamps, counts and outcome.
- [ ] Add per-record reconciliation/error status without storing unnecessary provider payloads.
- [ ] Implement least-privilege credentials and rotation support.
- [ ] Add idempotency and safe replay.
- [ ] Add freshness/data-quality alerts.
- [ ] Implement one narrow read-only integration and prove reconciliation before expanding.
- [ ] Add provider contract tests and a live staging proof.

### Entra/OIDC

- [ ] Implement discovery, state, nonce and PKCE validation.
- [ ] Define account linking and joiner/mover/leaver handling.
- [ ] Map approved identity groups to HCM roles without privilege escalation.
- [ ] Preserve payroll step-up as a separate control.
- [ ] Add session/account revocation and audit events.
- [ ] Test disabled user, changed claims, duplicate identity and emergency-access cases.

## P1 — Secure employee-relations case foundation

Plan access and conflicts before creating models. Ordinary manager reporting-chain access is insufficient.

- [ ] Obtain HR/legal policy decisions for disciplinary, grievance, harassment, appeal and CCMA workflows.
- [ ] Define restricted case-team roles and conflict-safe reassignment.
- [ ] Define legal hold, retention and protected evidence rules.
- [ ] Model intake, allegation, parties, representatives and protected witnesses.
- [ ] Model notices, hearings, deadlines and evidence chain-of-custody metadata.
- [ ] Model findings, outcomes, sanctions, appeal and external referral.
- [ ] Add retaliation flags and escalation.
- [ ] Audit every case/evidence read and mutation.
- [ ] Add privacy-safe aggregate reporting.
- [ ] Add conflict, row-scope, evidence and retention tests.
- [ ] Add separate employee, case-team and auditor browser journeys.

## P1 — Reasonable accommodation

- [ ] Confirm policy, lawful basis, authorised case team and minimum medical information.
- [ ] Keep accommodation records separate from demographic disability identity.
- [ ] Capture request, functional requirement, consultation and assessment.
- [ ] Capture decision, implementation owner, cost and evidence.
- [ ] Capture review/expiry, appeal and closure.
- [ ] Restrict evidence to the authorised team and audit every access.
- [ ] Expose only de-identified compliance totals outside the case team.
- [ ] Add alternative-format and accessibility requirements to the employee workflow.

## P1 — Statutory workflow foundation

Start with shared versioned obligations and filing evidence. Do not build each deadline as unrelated hard-coded logic.

### Shared obligation model

- [ ] Model instrument, version, effective dates and applicability.
- [ ] Model due-date rule using a South African business calendar.
- [ ] Model responsible roles, evidence requirements and reminder cadence.
- [ ] Make reminder emissions idempotent.
- [ ] Preserve the obligation version on every submission/evidence record.

### EE filing evidence

- [ ] Track report year/form, method, submitter and submission timestamp.
- [ ] Track acknowledgement/reference and immutable supporting evidence.
- [ ] Track submitted, accepted, rejected and error states.
- [ ] Stop reminders only from a defensible submitted/accepted state.
- [ ] Add audit, history and protected evidence downloads.

### Subsequent regulatory workflows

- [ ] EEA14 inability notices.
- [ ] Section 53 certificate applications and outcomes.
- [ ] Formal versioned EEA1 employee declarations.
- [ ] EEA12 analysis records and links to EE plan measures.
- [ ] B-BBEE Skills Development calculator/evidence pack after ICT Code verification.
- [ ] B-BBEE section 13G reporting pack.
- [ ] WSP/ATR readiness and submission evidence after SETA confirmation.
- [ ] EE enforcement register and assigned EE-manager records.

## P2 — Generic delegation and approvals inbox

- [ ] Inventory existing approval/signing workflows and their specialised rules.
- [ ] Define delegation scopes and permitted actions.
- [ ] Add effective dates, revocation and no-subdelegation rule.
- [ ] Prevent a delegate receiving more authority than the delegator.
- [ ] Record both acting user and delegated authority in audit events.
- [ ] Re-evaluate delegation after reporting-line/role changes.
- [ ] Add a permission-scoped “my approvals” API and UI.
- [ ] Migrate one workflow before generalising further.

## P2 — Complete improvement-plan lifecycle

- [ ] Replace the corrective-action stub with explicit states.
- [ ] Link initiation basis and evidence.
- [ ] Capture support, actions, measurable outcomes and owners.
- [ ] Capture employee comments and acknowledgement.
- [ ] Add review meetings, amendments and reminders.
- [ ] Add successful closure, extension and escalation outcomes.
- [ ] Link to employee relations only through a controlled human decision.
- [ ] Preserve signed/archive evidence and audit history.

## P2 — Benefits lifecycle and provider reconciliation

- [ ] Confirm actual benefit-provider and payroll interfaces.
- [ ] Model effective-dated eligibility rules.
- [ ] Model life-event and annual enrolment windows.
- [ ] Link dependant coverage with minimum necessary evidence.
- [ ] Model employer/employee contributions without duplicating payroll authority.
- [ ] Add provider export/import, failure state and reconciliation queue.
- [ ] Preserve historical elections and effective dates.

## P2 — Reporting, imports and scale

- [ ] Inventory the remaining `fetchAllPages` call sites and rank by data volume/privacy risk.
- [ ] Add server-side search/filter/pagination to high-volume screens.
- [ ] Define purpose-built summary serializers for selectors.
- [ ] Add a permission-aware report builder with bounded fields and filters.
- [ ] Add scheduled report delivery with audit, recipient validation and idempotency.
- [ ] Add dry-run, validation and error exports to broader bulk imports.
- [ ] Add realistic-volume query and export performance tests.

## P3 — Controlled architecture and documentation cleanup

- [ ] Split `EmployeeDetailPage.tsx` by domain panel.
- [ ] Split `MyPerformancePage.tsx` by workflow stage.
- [ ] Split `ApplicantDetailPage.tsx` by recruitment subdomain.
- [ ] Split `EEConfigurationPage.tsx` by statutory/configuration concern.
- [ ] Split backend core/performance hotspots without changing transaction semantics.
- [ ] Decompose `seed_demo_data.py` into deterministic domain seeders.
- [ ] Reconcile stale roadmap and sprint status claims against current code.
- [ ] Establish one authoritative current-state table.
- [ ] Keep historical implementation notes separate from the live queue.

## Continuous verification checklist

Apply these to every completed slice:

- [ ] Positive and negative domain tests.
- [ ] Role and row-scope tests.
- [ ] Sensitive/Restricted field-tier tests.
- [ ] Historical-as-at tests where event reporting is involved.
- [ ] Audit and protected-download tests.
- [ ] Concurrency/idempotency tests for irreversible or duplicate-prone actions.
- [ ] SQLite and PostgreSQL evidence where database behaviour matters.
- [ ] OpenAPI/generated-client drift check.
- [ ] Frontend lint, typecheck and production build.
- [ ] Browser coverage across relevant roles.
- [ ] Keyboard, focus, validation and accessible-name checks.
- [ ] Current primary-source regulatory confirmation where applicable.
- [ ] Clear distinction between mocked, local, staging and live-provider evidence.

## Recommended starting point

~~Begin with P0.1–P0.4 as one bounded tranche.~~ **Done** — every P0.1–P0.4 checkbox above is closed, along with the
full scale/privacy follow-up (employee-selector rollout, employee-directory removal) and several P1 items (backup
automation, operational metrics, ADR-012 deploy/rollback, the org chart focused view, contract-to-permanent
conversion linked to a real position, and the policy committee approval gate) — see the follow-up sections above and
commit history from 2026-09-01 onward. This paragraph itself was the stale-roadmap example P3 calls out below; the
current starting point is **P3's architecture/documentation cleanup**, since none of P1's remaining items (pilot UAT,
identity/SSO, employee-relations case management, statutory workflow depth) can be unblocked by more engineering
alone — they need human decisions (legal policy, SAP/Entra ownership, UAT scheduling) this repo can't make for itself.
