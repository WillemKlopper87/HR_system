# HR/HCM codebase evaluation and critique

**Reviewed and regenerated:** 2026-08-28
**Scope:** `C:\applications\HR_system`, frontend through backend, assessed as a South African enterprise HR/HCM system.
**Review basis:** Current code, tests, CI, architecture documents and live backlog state. Older roadmap claims were checked against code because several have become stale as later capabilities shipped.

## Executive assessment

This is a substantial modular HCM platform, not a basic employee database. It has strong foundations in effective-dated
employee records, establishment control, recruitment, onboarding/offboarding, performance contracting, compensation,
learning, succession, employee documents, POPIA requests, Employment Equity reporting, auditability and tiered RBAC.

Its biggest remaining weaknesses are not basic CRUD. They are production integration, statutory workflow evidence,
case-management depth, scale-oriented frontend architecture and stakeholder validation. The system is suitable for a
controlled pilot after operational and UAT gates, but should not yet be treated as a complete replacement for payroll,
leave/time systems, identity infrastructure or formal employee-relations case management.

| Area | Assessment | Principal gap |
|---|---|---|
| Core employee record and lifecycle | Strong | External system reconciliation and broader workflow orchestration |
| Security, privacy and audit | Strong | SSO not implemented; some sensitive case domains remain absent |
| Recruitment and onboarding | Strong | Deeper offer/pay controls and production provider integrations |
| Performance and talent | Strong | Corrective action is a stub; no generic delegation/approval inbox |
| Compensation and benefits | Good | Not payroll; provider/payroll integration and employee query workflow are thin |
| EE and regulatory reporting | Good foundation | Filing, acknowledgement and regulatory evidence workflows are incomplete |
| Employee relations | Weak/absent | Disciplinary, grievance, harassment and accommodation cases |
| Frontend architecture | Moderate | Manual API types, large pages, eager route loading and all-page fetches |
| Backend architecture | Good but growing | Large core/performance modules and cross-app workflow coupling |
| Testing | Strong backend, moderate browser depth | New regulatory workflows and some long journeys lack stable coverage |
| Production readiness | Moderate | UAT, live integrations, automated recovery evidence and deployment proof |

## Current verification evidence

At the reviewed `0d27f04` state:

- Django system checks passed.
- Migration-drift check reported no changes.
- The complete backend suite passed: **1,182/1,182**.
- Frontend lint, TypeScript compilation and production build passed.
- Frontend still reports two Fast Refresh warnings.
- The production build still reports large main and identity-verification chunks.
- The new probation, exit, evidence-download and regulatory-dashboard workflows do not yet all have browser coverage.

## Strengths to preserve

### Data integrity and history

- `EmployeeVersion` provides effective-dated employee state instead of overwriting the past.
- Lifecycle changes, contract renewals and exits are explicit workflows rather than untracked field edits.
- Positions and employee occupancy are separated, supporting establishment and vacancy control.
- Regulatory event reports now resolve employee/applicant attributes as at the relevant event date.
- Signed performance and probation artefacts retain timestamps, actors and content hashes.

### Security and privacy

- DRF is deny-by-default and uses explicit role/row-scope permissions.
- Data is classified into field tiers, including Restricted payroll information.
- Payroll data requires a scoped TOTP step-up grant.
- Protected document and evidence downloads are authenticated, row-scoped and audited.
- Aggregate demographic reporting applies shared complementary small-cell suppression.
- Access-matrix tests exercise viewsets across roles.
- POPIA export and erasure request workflows exist, with human review rather than blind deletion.

### HR capability breadth

- Core employee profiles, org structure and establishment.
- Recruitment, public applications, interview panels, scorecards and background checks.
- Contract renewal, probation, employment changes and exit interviews.
- Onboarding and offboarding checklists with lifecycle hooks.
- Performance agreements, evidence, reviews, signatures, calibration and 360 feedback.
- Salary-review cycles, compensation proposals, benefits and total-rewards statements.
- Course catalogue, training records, mandatory-training compliance and skills inventory.
- Succession planning, critical posts and talent pools.
- Policies, acknowledgements, audit viewer, notifications and data-quality registry.
- EE plans, forum records, reports and demographic dashboards.
- Employee documents, qualifications, dependants, emergency contacts and POPIA requests.

These are valuable foundations. Future work should extend them rather than introduce parallel models for the same facts.

## Frontend critique

### 1. The generated API contract is not being consumed

The frontend contains a generated OpenAPI type file of roughly 13,000 lines, but no frontend source file imports it.
Instead, 63 source files import the approximately 2,000-line handwritten `api/types.ts` file.

Consequences:

- API changes can regenerate successfully while handwritten UI types silently drift.
- Response shapes, enums and nullability have two sources of truth.
- New endpoints require manual type maintenance even though code generation already exists.
- Contract errors are found in browser testing instead of at compile time.

Improvement:

1. Add a thin domain-friendly type facade over `generated-types.ts`.
2. Keep presentation-only labels/constants separate from transport types.
3. Migrate one module at a time, beginning with a small dashboard or probation.
4. Add a CI assertion that production source imports generated types or approved facade types.
5. Delete replaced declarations from `api/types.ts` incrementally.

### 2. Pagination is defeated by broad `fetchAllPages` usage

The backend correctly uses cursor pagination with a page size of 50, but the frontend has approximately 118
`fetchAllPages` references. Many screens load every employee and every related record to populate local selectors.

This will degrade as staff and history grow:

- slow initial loads and high memory use;
- repeated organisation-wide employee downloads;
- unnecessary exposure of rows to broad pages;
- weak search experience;
- large bursts of sequential cursor requests.

Improvement:

- implement server-side search/filter endpoints for employee and reference pickers;
- add debounced async comboboxes;
- retain cursor paging in list screens;
- create purpose-specific lightweight summaries rather than returning full employee records;
- measure and set query-count/performance budgets for large organisations.

### 3. Only one route is code-split

`MyIdentityVerificationPage` is lazy-loaded, while the rest of the application is eagerly imported through
`App.tsx`. The build still warns about the main bundle and the face-recognition chunk.

Improvement:

- lazy-load by functional area: recruitment, performance, EE, compensation, talent and employee self-service;
- load face-recognition assets only after the employee opens the capture workflow;
- add route-level error boundaries and useful loading skeletons;
- enforce a documented chunk-size budget rather than suppressing the warning.

### 4. Several pages are too large

Examples:

- `EmployeeDetailPage.tsx`: about 1,253 lines;
- `MyPerformancePage.tsx`: about 1,202 lines;
- `ApplicantDetailPage.tsx`: about 976 lines;
- `EEConfigurationPage.tsx`: about 810 lines;
- `MyDocumentsPage.tsx`: about 573 lines.

These pages combine data fetching, permissions, mutations, forms and many separate business workflows. Extract tabs
and workflow panels into domain components and hooks. Avoid generic abstractions until two genuine consumers share a
pattern.

### 5. Shared hooks are useful but only partially adopted

`useApiQuery` is used in about 34 files and `useMutation` in only about six. Many older screens still hand-roll
effects, state and error handling. Continue migration while adding:

- request cancellation with `AbortController`, not only stale-result suppression;
- standard field-error mapping from DRF responses;
- mutation invalidation/refetch conventions;
- accessible global success/error announcements;
- predictable empty, denied and unavailable states.

### 6. Accessibility and responsive behaviour require a systematic pass

The UI has browser coverage, but no evidence of a full WCAG audit across role-specific forms, modals, tables and
face-capture flows. HR users also need usable mobile/tablet workflows for interview panels, approvals, attendance and
checklists.

Plan a measured WCAG 2.2 AA pass with keyboard, screen-reader, zoom/reflow, error-summary, focus-management and
high-contrast evidence. Treat biometric capture as a specialised accessibility workflow with a non-biometric fallback.

## Backend critique

### 1. Production system integrations remain incomplete

The current remuneration CSV is explicitly a stand-in for SAP payroll. Leave is not integrated. OIDC/Entra is noted
in comments and architecture decisions but authentication remains Django session based. The assessment provider uses
an adapter structure but no real contracted provider.

These are appropriate boundaries if SAP and Entra remain systems of record, but they need production-grade adapters:

- immutable source-system identifiers and reconciliation status;
- incremental sync, retry, dead-letter and replay controls;
- source timestamps and effective dates;
- conflict handling and manual exception queues;
- least-privilege service credentials and rotation;
- audit evidence for every inbound change;
- monitoring and freshness alerts.

Do not build a second payroll or leave engine unless the organisation explicitly changes the system-of-record decision.

### 2. Employee-relations case management is absent

There is no dedicated disciplinary, grievance or CCMA case domain. Exit reasons and EE reporting constants are not a
substitute for confidential case management.

A defensible employee-relations module should include:

- confidential intake with conflict-safe routing;
- allegations, parties, representatives and protected witnesses;
- hearings, notices, evidence and chain-of-custody metadata;
- outcomes, sanctions, appeals and review dates;
- CCMA/bargaining-council referrals and deadlines;
- retaliation flags, legal hold and restricted retention;
- strict case-team access rather than ordinary manager row scope;
- aggregate reporting that never exposes case identities.

Harassment should use the same secure case foundation but have specialised privacy and retaliation controls.

### 3. Reasonable accommodation needs its own protected workflow

Disability demographic identity is not the same as an accommodation case. Build a separately authorised register for:

- request and acknowledgement;
- functional requirement rather than unnecessary diagnosis detail;
- assessment and consultation;
- decision, implementation owner and cost;
- review/expiry dates and appeal;
- confidential supporting evidence;
- de-identified compliance reporting.

Medical detail should not flow into ordinary employee profiles or EE dashboards.

### 4. Regulatory reporting stops short of submission evidence

The system produces strong internal EE data and frozen reports, but it does not yet model the complete statutory
workflow:

- actual EEA2/EEA4 filing and acknowledgement state;
- EEA14 inability notices;
- section 53 certificate applications/outcomes;
- formal EEA1 declarations;
- EEA12 analysis records;
- versioned obligations and due-date rules;
- B-BBEE Skills Development evidence packs;
- section 13G and WSP/ATR readiness records.

The next regulatory slice should store evidence of submission/acceptance and never infer filing from internal sign-off.
Current requirements and deadlines must be reconfirmed from official primary sources before implementation.

### 5. Generic delegation and approval orchestration are missing

Performance has specialised signing delegation, while other approval and manager workflows implement their own rules.
A generic scoped delegation model and “my approvals” inbox would reduce duplicated logic and support acting managers.

The model must define:

- scope and permitted actions;
- effective dates and revocation;
- delegator/delegate constraints;
- whether sub-delegation is forbidden;
- audit attribution to both actor and authority source;
- no expansion beyond the delegator's own authority;
- interaction with reporting-chain changes.

### 6. Corrective performance action is still a stub

`ImprovementPlan` is explicitly described as a corrective-action stub. It needs a real lifecycle if performance
management is to be relied upon:

- initiation basis and linked evidence;
- agreed actions, support and measurable outcomes;
- employee comments and acknowledgement;
- review meetings and amendments;
- outcome, extension, successful closure or escalation;
- controlled linkage into employee relations without automatic punitive action.

### 7. Benefits management is shallow compared with compensation

Benefits, elections and total-rewards display exist, but a mature benefits domain may also require:

- eligibility and effective-dated plan rules;
- life-event enrolment windows;
- dependant coverage and evidence;
- employer/employee contribution calculations;
- provider export/import and reconciliation;
- pending/failed provider enrolment status;
- historical elections and annual renewal.

This should be driven by actual payroll/provider interfaces rather than speculative internal calculations.

### 8. Large modules need controlled decomposition

Backend hotspots include `core_hr/models.py`, `core_hr/views.py`, `performance/views_agreements.py` and
`performance/services/agreements.py`. Split by lifecycle/use case while preserving explicit transaction boundaries,
row-scope checks, audit events and history creation.

The 1,600-line demo seed command should also be decomposed into deterministic per-domain seeders with an orchestration
command. This would reduce conflicts and make e2e fixtures easier to reason about.

## Security, privacy and operational critique

### Identity

- Implement real Entra/OIDC SSO with tenant/domain controls and account-linking rules.
- Define joiner/mover/leaver account provisioning and emergency access.
- Keep payroll step-up separate from ordinary SSO login assurance.
- Establish session/device revocation and administrator visibility if not already covered by the identity provider.

### Biometrics

The identity-verification module uses face descriptors and geolocation. Before production, document and validate:

- lawful basis and necessity;
- explicit employee notice/consent where applicable;
- biometric retention and deletion;
- encryption and restricted support access;
- false-match/no-match thresholds across the workforce population;
- device/browser support;
- non-biometric alternatives;
- human review and appeal procedures.

The current human-review requirement is a good safeguard and must remain.

### Operations

Logging, readiness checks, optional Sentry and a backup/restore runbook exist. Remaining evidence gaps include:

- automated scheduled backups and off-site retention;
- a recorded restore rehearsal, including media and hashes;
- metrics, dashboards and alerts beyond error capture;
- staging deployment and production topology evidence;
- secrets management and rotation procedures;
- capacity/load testing with realistic employee history and documents;
- disaster recovery objectives and ownership;
- external integration monitoring and reconciliation queues.

## Testing critique

The project has unusually strong backend coverage and tests both SQLite and PostgreSQL in CI. Important remaining gaps:

- browser coverage for probation signing, exit interviews, demographic dashboards and protected evidence downloads;
- stability of long performance browser journeys;
- accessible keyboard/screen-reader coverage;
- provider-contract tests for SAP, Entra and any assessment vendor once selected;
- large-dataset performance tests for employee selectors, dashboards and exports;
- backup/restore and migration rehearsals in a production-shaped environment;
- negative browser tests confirming that hidden UI actions are also refused by the API.

CI uses mutable GitHub Action tags such as `actions/checkout@v4`; pin third-party actions to reviewed commit SHAs for
stronger supply-chain control.

## Documentation and governance critique

The documentation is valuable but partially stale:

- `ROADMAP-2026-08.md` still describes capabilities such as C2 and onboarding/offboarding as unbuilt even though code
  and newer sprint documents show they shipped.
- Status is spread across the roadmap, sprint index, sprint detail files, session state and next-agent brief.
- Some old verification counts and “not started” labels no longer represent the current repository.

Create one authoritative current-state table and keep historical implementation notes append-only elsewhere. A future
agent should never need to infer current scope from contradictory documents.

## Prioritised recommendation order

1. Stakeholder UAT, security/privacy review and deployment-readiness gap closure.
2. Frontend generated-type adoption, server-side selectors and route-level code splitting.
3. Real Entra/OIDC identity integration and joiner/mover/leaver provisioning.
4. SAP payroll and leave read-only integration with reconciliation and freshness monitoring.
5. Employee-relations/harassment secure case-management foundation.
6. Reasonable-accommodation workflow.
7. Regulatory filing, acknowledgement and obligation evidence foundation.
8. Generic delegation and “my approvals” inbox.
9. Complete improvement-plan/corrective-action lifecycle.
10. Benefits provider integration and effective-dated eligibility lifecycle.
11. Report builder, scheduled reports and broader bulk import/export.
12. Backend/frontend module decomposition and documentation consolidation throughout the above work.

## Next-agent planning brief

The next agent should not implement the entire list as one sprint. Reconcile current Git and current sprint documents,
then prepare independently verifiable tranches.

### Tranche 1 — frontend scalability and contract integrity

Objective: make the current UI safer at organisational scale without changing HR policy.

Plan:

1. Separate transport types from display labels in `api/types.ts`.
2. Create a generated-type facade and pilot it on probation or exit interviews.
3. Add server-side employee search/summary endpoints for selectors used by that pilot.
4. Replace `fetchAllPages('/employees/')` with a debounced paged combobox.
5. Lazy-load the pilot functional area and add a route error boundary.
6. Split the two React context non-component exports to clear Fast Refresh warnings.
7. Add browser tests for permitted and denied workflow roles.

Exit criteria:

- pilot screens import generated/facade transport types;
- no organisation-wide employee fetch is needed for their selectors;
- no new manual API response interface is introduced;
- lint/typecheck/build pass without the two current warnings;
- chunk size is measured and improved;
- focused browser tests pass.

### Tranche 2 — UAT and production-readiness gate

Objective: turn extensive automated evidence into an accountable pilot decision.

Plan:

- execute role-based walkthroughs with HR, talent, EE, compensation, audit and employee representatives;
- perform privacy review of biometrics, disability data, union representation and protected documents;
- test restore into an isolated environment and verify database/media hash consistency;
- capture concurrency and response-time baselines with realistic volumes;
- record all findings in one triaged UAT backlog with owner and severity;
- block production reliance on unresolved critical findings.

### Tranche 3 — identity and system-of-record integrations

Objective: eliminate CSV/manual identity dependencies without duplicating payroll or leave.

Planning decisions required:

- Entra tenant, claim mapping, group/role source and account-linking rules;
- SAP integration method, source objects, delta mechanism and ownership;
- leave source system and freshness expectation;
- authoritative field ownership for every synchronised attribute;
- failure, replay, reconciliation and rollback procedures.

Implement framework and one narrow read-only sync first. Do not broaden until reconciliation evidence is proven.

### Tranche 4 — secure employee-relations case foundation

Objective: build one privacy-safe case platform reusable for disciplinary, grievance and harassment workflows.

Plan access and conflict rules before models or screens. Ordinary line-manager row scope is not sufficient. Include
restricted case teams, legal hold, evidence access logging, deadlines, human decisions, appeal and aggregate reporting.

### Tranche 5 — statutory workflow foundation

Objective: distinguish internal report preparation from defensible submission and acceptance evidence.

Start with versioned regulatory obligations and an EE submission record. Add EEA14 and section 53 workflows only after
official-source requirements are reconfirmed. Reuse protected evidence-download, audit and reminder infrastructure.

### Subsequent tranches

- Reasonable accommodation.
- Generic delegation and approval inbox.
- Improvement-plan lifecycle.
- Benefits-provider integration.
- Reporting/export scale work.
- Module and documentation consolidation.

## Verification gates for every tranche

- Preserve effective dating, audit events and simple-history records.
- Add positive, negative, role, row-scope, field-tier and historical-as-at tests as applicable.
- Add concurrency tests for signing, approval, booking or import workflows.
- Run `manage.py check --fail-level WARNING` and migration-drift checks.
- Run affected tests and the complete backend suite on SQLite and PostgreSQL where relevant.
- Regenerate OpenAPI and frontend generated types for contract changes.
- Run frontend lint, TypeScript and production build.
- Add Playwright coverage for user-visible workflows across relevant roles.
- Add accessibility verification for new interactions.
- Distinguish mocked integration tests from live staging evidence.
- Update the authoritative backlog, data dictionary, RBAC documentation and session handoff.
- Reconfirm current legal/regulatory facts from primary official sources before encoding rules or deadlines.

## Recommended immediate action

Start with Tranche 1 as a focused implementation slice, then run Tranche 2 before adding another large HR domain. This
reduces near-term scale and contract risk while giving stakeholders a stable system on which to perform meaningful UAT.
