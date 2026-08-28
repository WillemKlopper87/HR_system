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

Verification evidence:

- Full Django suite: 1,184 tests passed.
- Focused employee API suite: 9 tests passed.
- Focused Playwright suite: 2 tests passed.
- Django system check and migration drift check passed.
- Frontend lint, TypeScript compilation and production build passed.
- `git diff --check` passed; only Git's expected LF-to-CRLF notices were emitted.

Items left unchecked below remain outstanding; in particular, the complete probation/exit workflow browser matrix,
route-level error boundaries, contract-import enforcement, obsolete handwritten-type removal and chunk-budget policy.

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
- [ ] Remove the replaced handwritten declarations from `src/api/types.ts`.
- [ ] Add a CI/source check preventing migrated modules from importing their removed handwritten transport types.
- [ ] Document the migration pattern for later modules.

### P0.2 Scalable employee selector

- [x] Define a privacy-minimal employee-search response: identifier, employee number, display name and only the fields
      required by an authorised selector.
- [x] Confirm each selector's role and row-scope requirements before sharing an endpoint.
- [x] Add server-side search with cursor pagination and a bounded page size.
- [ ] Add tests for empty query, partial match, pagination, role denial and reporting-chain scope.
- [x] Add a debounced accessible async employee combobox.
- [x] Replace `fetchAllPages<Employee>('/employees/')` in probation and exit-interview screens.
- [x] Ensure stale searches are cancelled with `AbortController`.
- [x] Verify that a selector never downloads unrelated employee detail fields.

### P0.3 Route splitting and frontend warning cleanup

- [x] Move non-component exports out of `AuthContext.tsx`.
- [x] Move non-component exports out of `ReferenceDataContext.tsx`.
- [x] Lazy-load the probation and exit-interview routes.
- [ ] Add a shared route loading state and route-level error boundary.
- [x] Measure main and relevant route chunks before and after the change.
- [ ] Record a chunk-size budget and fail or warn consistently when it regresses.

### P0.4 Browser coverage for the regulatory workflows

- [ ] HR opens a valid probation period.
- [ ] HR is refused invalid/overlapping probation dates.
- [ ] Correct line manager creates a review.
- [ ] Unrelated manager is refused the review.
- [ ] Employee countersigns using their own password.
- [ ] Manager and HR are refused employee countersignature.
- [ ] HR records an exit interview with a valid single trigger.
- [ ] Mismatched or multiple exit triggers are refused.
- [ ] Authorised user downloads protected training evidence.
- [ ] Unrelated employee is refused the evidence download.
- [ ] Demographic dashboards render suppression without reconstructable values.
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
- [ ] Update backlog, session state, API/data dictionary and RBAC documentation where applicable.

## P1 — Pilot readiness and accountable UAT

This is the highest-value organisational gate. It can be planned alongside P0, but stakeholder evidence cannot be
manufactured by engineering.

- [ ] Create role-based walkthroughs for employee, manager, HR, recruiter, compensation, EE and auditor personas.
- [ ] Run HR/talent/EE/compensation stakeholder UAT.
- [ ] Run security review of authentication, step-up, downloads, audit and lifecycle cascades.
- [ ] Run privacy review of biometrics, disability data, union representation and protected documents.
- [ ] Verify non-biometric identity/check-in alternative and appeal procedure.
- [ ] Record findings with severity, owner, target date and production-blocking flag.
- [ ] Resolve all critical findings before production reliance.
- [ ] Record formal pilot acceptance or rejection and its scope.

### Operational evidence

- [ ] Automate scheduled database and media backups with off-site retention.
- [ ] Restore both into an isolated environment.
- [ ] Verify recent signed artefact hashes after restore.
- [ ] Record restoration duration and define RPO/RTO ownership.
- [ ] Add metrics for API errors, latency, task failures, notification failures and integration freshness.
- [ ] Add dashboards and actionable alerts.
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

Begin with **P0.1–P0.4 as one bounded tranche**. It is the strongest immediate win because it improves frontend/backend
contract integrity, removes organisation-wide employee downloads, reduces bundle/warning debt and closes known
regulatory browser gaps without waiting for SAP, Entra, legal policy or an external vendor.
