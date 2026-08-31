# HR/HCM recommended improvements and competitive-readiness report

**Prepared:** 2026-08-31  
**Repository:** `C:\applications\HR_system`  
**Code baseline:** `e669faa` (`feat: role-adaptive overview dashboard frontend`)  
**Primary evidence:** current source, tests, CI and `updated_codebase_audit.md`

## 1. Purpose and assessment boundary

This report translates the current codebase audit and external-product benchmark into an implementation programme. It
addresses four questions:

1. How should functional coverage be improved?
2. How should usage and user experience be improved?
3. How should features and competitive position be improved?
4. What is required for credible enterprise readiness?

It then identifies the fastest route to measurable improvement. The recommendations distinguish between software that
exists in source, software that works in a controlled environment, and capabilities proven under production conditions.
The review is not a legal opinion, payroll certification, penetration test, WCAG certification or proof of actual user
adoption. Production telemetry, formal user research and live integration evidence were not available.

## 2. Executive recommendation

The system should be positioned as a **South Africa-focused modular HCM platform with strong governance foundations**,
not yet as a complete payroll or globally proven enterprise HCM suite. Its best competitive path is not to reproduce
every feature in Workday, SAP SuccessFactors or Oracle HCM. It should become exceptionally good at:

- trusted employee and organisational records;
- South African employment-equity, skills-development and POPIA workflows;
- auditable employee lifecycle decisions;
- secure manager and employee self-service;
- clean integration with payroll, leave, identity and finance systems; and
- transparent evidence for regulated and high-risk HR processes.

The current platform has broad HR coverage, but enterprise adoption will be constrained by four cross-cutting gaps:

1. workforce-scale data access has not been proven;
2. personas, permissions and dashboard experiences are not consistently aligned;
3. authoritative identity, payroll and leave integrations are not live and reconciled; and
4. deployment, recovery, performance, accessibility and operational support lack completed evidence.

The fastest improvement route is therefore **stabilise, simplify, integrate, prove, then expand**. New feature volume
should not outrun the shared access-control, case-security and operational foundations.

### Target movement

| Dimension | Current | Realistic near-term target | Evidence required for target |
|---|---:|---:|---|
| Functional coverage | 7.5/10 | 8.5/10 | Priority gaps delivered without duplicating payroll/leave authorities |
| South African relevance | 8/10 | 9/10 | Legal review, filing evidence and source reconciliation |
| Usage and user experience | 5.5/10 | 7.5/10 | Task-based UAT, accessibility checks and measurable journey improvements |
| Reporting and analytics | 6/10 | 7.5/10 | Self-service reporting, scheduled delivery and governed metric definitions |
| Integrations | 3.5/10 | 7/10 | Live Entra, payroll and leave sync with reconciliation and replay |
| Scalability | 4.5/10 | 7.5/10 | Set-based scoping, true pagination and representative load evidence |
| Enterprise operations | 4/10 | 7/10 | Immutable deployment, restore rehearsal, observability and support ownership |
| Overall versus mid-market HRIS | 7/10 | 8/10 | Production pilot and referenceable user outcomes |
| Overall versus Tier-1 enterprise HCM | 4.5-5/10 | 6-6.5/10 | Proven scale, integrations and operations; not feature-count parity |

## 3. Coverage improvements

### 3.1 Preserve and deepen existing strengths

Existing effective-dated employee records, establishment controls, recruitment, lifecycle workflows, performance,
learning, succession, compensation, policy acknowledgement, POPIA requests, Employment Equity reporting, protected
documents and auditability should remain the product core. Improvements should preserve:

- history rather than destructive overwrites;
- explicit workflow transitions and signatures;
- row and field-level access controls;
- authenticated evidence access and immutable audit trails;
- small-cell suppression on sensitive demographic reporting; and
- a modular-monolith design until scale evidence justifies a different deployment topology.

Every new module should reuse those foundations rather than introduce independent employee, document, permission or
notification concepts.

### 3.2 Employee relations and labour-case management

**Gap.** There is no complete restricted workflow for disciplinary, grievance, harassment, protected disclosure,
appeal or CCMA-related cases. Ordinary manager reporting-line access is unsafe for allegations, witnesses and conflicts.

**Recommended capability.**

- confidential intake with case classification and severity;
- an explicit case team, conflict declaration and reassignment process;
- parties, representatives and protected witness identities;
- notices, hearings, postponements, deadlines, findings and sanctions;
- appeal and external referral tracking;
- evidence hashes, custody events, access history and legal hold;
- links to performance and employment-change records without copying sensitive detail; and
- restricted exports with purpose, approval and watermarking.

**Prerequisite.** HR, legal, privacy and security must approve the case access matrix, retention policy, subject-access
rules and segregation between allegation, investigation and outcome data before implementation.

**Success evidence.** Access-matrix tests cover conflicts and multi-role users; a seeded case completes intake through
appeal; forbidden users cannot infer case existence through counts, search, notifications or audit exports.

### 3.3 Reasonable accommodation and disability support

**Gap.** Demographic and disability information exists, but a purpose-limited accommodation process does not.

**Recommended capability.**

- confidential request and consent capture;
- functional-needs information separated from diagnosis or unnecessary medical detail;
- interactive assessment, decision, review date and appeal;
- equipment, workplace and cost actions with responsible owners;
- highly restricted supporting documents;
- disclosure preferences and manager-facing minimum-necessary instructions; and
- retention and deletion rules distinct from the general employee file.

**Success evidence.** Managers can see only approved workplace actions, not medical evidence; privacy and accessibility
owners sign off the workflow; audit records prove every sensitive access.

### 3.4 HR service-delivery portal

**Gap.** Employees use separate module-specific journeys and HR lacks a unified service queue.

**Recommended capability.**

- service catalogue covering records, benefits, payroll queries, policies and employment letters;
- structured intake, priority, SLA, assignment and escalation;
- secure conversation and attachment handling;
- knowledge articles and guided forms;
- employee-visible status and expected response date;
- automatic linkage to the relevant authoritative record; and
- operational reporting for demand, backlog, age and repeat-contact rate.

Sensitive employee-relations or accommodation cases must not be downgraded into general service tickets. Intake should
route them into their protected domains.

**Success evidence.** Users can submit and track common requests without email; HR can measure SLA performance; case
visibility follows both role and case assignment.

### 3.5 Payroll, leave and time boundaries

**Gap.** Compensation workflows are substantial, but the system is not a payroll engine and does not provide complete
leave, time or attendance processing.

**Recommendation.** Keep payroll and leave authoritative externally unless a separate strategic decision funds their
full legal and operational ownership. Build governed integration instead:

- versioned employee, position and remuneration outbound contracts;
- payroll-result and leave-balance inbound contracts;
- effective-date validation and duplicate protection;
- source cursor, correlation ID and per-record status;
- reconciliation totals and exception work queues;
- replay that is idempotent and preserves the original evidence;
- freshness indicators on employee and operator screens; and
- explicit treatment of retroactive changes and terminated employees.

**Success evidence.** Parallel-run reconciliation meets agreed tolerances, every rejected record has an accountable
owner, and users can tell when displayed payroll or leave data was last confirmed by its source.

### 3.6 Workforce planning and organisation change

**Gap.** Establishment data exists, but there is no mature scenario-planning capability.

**Recommended capability.**

- proposed structures separate from approved structures;
- position and cost scenarios with effective dates;
- vacancy, skill, succession and retirement-risk views;
- approval and comparison of scenario versions;
- affordability inputs from finance without turning HCM into a general ledger;
- controlled conversion of an approved scenario into establishment changes; and
- impact reports covering affected incumbents and regulatory dimensions.

**Success evidence.** Planning cannot modify the live establishment before approval; finance and HR reconcile totals;
the final conversion creates traceable employment or position actions.

### 3.7 Learning, performance, benefits and talent depth

Existing modules should be completed before adjacent feature expansion:

- make performance-improvement plans a real lifecycle with milestones, evidence, review and closure;
- add learning sessions, attendance, providers, costs, evaluations and expiring-certification renewal;
- connect role and skill requirements to development plans and succession readiness;
- add benefit enrolment windows, life-event changes, beneficiaries and provider reconciliation;
- expose career paths and internal opportunities using approved position and skill data; and
- distinguish employee aspirations from management assessment and succession decisions.

## 4. Usage and user-experience improvements

### 4.1 Design around user tasks, not backend modules

The navigation and screens should be validated against the jobs of employee, manager, HR operations, recruiter,
performance administrator, learning administrator, compensation specialist, EE manager, auditor and executive.

For each persona, define its ten most frequent and five highest-risk tasks. Measure:

- completion rate;
- time and interaction count;
- validation and permission errors;
- abandonment and support contact;
- accessibility defects; and
- perceived confidence in the result.

This produces an evidence-based adoption baseline. Page views and logins alone should not be treated as successful use.

### 4.2 Make dashboards capability-adaptive

The overview currently derives an HR-admin, line-manager or employee presentation from broad row scope. Data scope and
business capability must be separated.

**Recommended design.**

- assemble widgets and actions from explicit capabilities;
- support additive multi-role experiences rather than selecting one persona bucket;
- show a task only if the user may complete its next action;
- distinguish personal, team, specialist and assurance views;
- use consistent empty, loading, stale-data and permission-denied states;
- avoid exposing sensitive queue counts to users without record access; and
- let users prioritise permitted widgets without changing authorization.

**Success evidence.** Browser tests cover every seeded persona and representative multi-role combinations. Every link
shown is reachable and authorised, and query counts remain within a budget.

### 4.3 Reduce page complexity

Oversized employee, performance, applicant and EE pages combine fetching, authorization, forms, tables and workflow
logic. Split them by coherent user task:

- a route-level container for identity and navigation;
- focused workflow panels or subroutes;
- domain hooks for server state and mutations;
- schema-based forms and reusable validation;
- local error boundaries for high-risk panels; and
- progressive disclosure for infrequent administrative fields.

Line count is a signal, not the acceptance criterion. The goal is isolated responsibilities, independent tests and
smaller cognitive load.

### 4.4 Replace eager list loading with real browsing

The frontend still contains 116 `fetchAllPages` references. Lists should use server-side search, filters, cursor
navigation, sorting and explicit export jobs. Priority order is applicants, employees and organisation views,
compensation, EE configuration, reviews, learning and succession.

Bulk export must be separate from interactive browsing, authorised independently and delivered as an audited,
asynchronous artifact when large.

**Success evidence.** Initial render does not retrieve the full dataset; filters remain encoded in the URL; selection
works across pages; representative 10,000-worker data does not cause browser memory or response-time degradation.

### 4.5 Standardise interaction and feedback

- Replace browser `prompt` and `confirm` calls with accessible, contextual dialogs.
- Standardise optimistic versus confirmed mutations by business risk.
- Preserve entered values after recoverable failures.
- Give validation messages at the field and summary level.
- Show request IDs for supportable server errors.
- Provide undo only where the underlying workflow safely supports it.
- Use plain-language status labels and explain why an action is unavailable.
- Add consistent skeleton, empty and stale-data states.

### 4.6 Accessibility and responsive use

Adopt WCAG 2.2 AA as the product target and make it part of definition of done:

- automated checks for every major route;
- keyboard-only task journeys;
- visible focus and logical focus restoration;
- accessible names and error announcements;
- contrast, zoom, reflow and reduced-motion checks;
- table alternatives and mobile-safe actions; and
- testing with representative assistive technology.

Automated scans are a floor, not certification. Formal evidence should include manual results and accountable sign-off.

### 4.7 Create an adoption and feedback loop

Add privacy-minimised product telemetry for journey completion, response time, errors, search success and feature use.
Do not record employee content, free text or sensitive field values in analytics. Combine telemetry with:

- task-based pilot UAT;
- structured employee and manager feedback;
- HR service-ticket themes;
- release-specific adoption targets; and
- a monthly usability and accessibility defect review.

## 5. Feature and competitive-position improvements

### 5.1 Competitive strategy

Tier-1 suites compete on global payroll, time, workforce planning, analytics, mobile experience, configurable workflows,
AI, marketplaces and implementation ecosystems. Workday describes a unified core HR, payroll, workforce-management and
analytics suite; SAP covers core HR, payroll, learning, talent and people intelligence; Oracle combines HR, talent,
workforce management, payroll and employee experience on a unified platform. BambooHR offers a polished connected
mid-market lifecycle, while Sage 300 People combines locally relevant payroll, HR, leave, self-service and statutory
reporting.

The project should compete through **local depth, transparent controls and integration flexibility**, not through an
unfunded claim of global parity.

### 5.2 Differentiators to strengthen

#### South African regulatory evidence

- turn EE and skills reports into evidence packs with source snapshot, calculation version, review, approval,
  submission reference and acknowledgement;
- reconcile regulatory totals to authoritative employee, payroll and training sources;
- version definitions and preserve the rule set used for each filing;
- maintain legal-owner review dates and change-impact records; and
- provide correction and resubmission workflows without overwriting prior evidence.

#### Auditable lifecycle decisions

- standardise decision records, reasons, attachments, approvals and signatures across probation, contracts,
  compensation, performance and exits;
- add delegation with dates, scope, conflict controls and auditability;
- provide a unified approvals inbox while preserving domain authorization; and
- expose human-readable decision history to authorised users.

#### Integration transparency

- show source, last confirmed time and reconciliation status beside imported data;
- make failed syncs visible and actionable rather than silently retried forever;
- publish stable API contracts and deprecation rules; and
- offer documented outbound events for approved consumers.

### 5.3 Reporting and analytics

Operational dashboards should evolve into a governed analytics layer:

- define a metric catalogue with owner, formula, grain, exclusions and privacy rules;
- provide saved filters, role-safe reports and scheduled distribution;
- add asynchronous export for large datasets;
- support trend, cohort and movement analysis;
- separate operational live metrics from frozen statutory snapshots;
- enforce minimum-cell and secondary suppression where inference remains possible; and
- create a warehouse or read model only when query and history requirements justify it.

Predictive attrition, generative summaries and automated recommendations should wait until data quality, purpose,
explainability, bias review and human oversight are demonstrably mature.

### 5.4 Configurability without uncontrolled complexity

Add configuration where organisations genuinely vary:

- workflow deadlines and reminders;
- approved reason and category catalogues;
- form templates and evidence requirements;
- notification templates with versioning;
- role-safe dashboard composition; and
- approval rules based on documented organisational attributes.

Avoid a universal no-code engine initially. Domain-specific configuration is easier to validate, secure and support.

### 5.5 API and extension ecosystem

- complete migration from handwritten frontend transport types to generated contracts;
- maintain backward-compatible public integration endpoints;
- provide scoped service credentials, rate limits and audit logs;
- implement signed webhooks with replay protection and delivery history;
- publish sandbox fixtures and conformance tests; and
- version schemas and announce deprecation windows.

## 6. Enterprise-readiness improvements

### 6.1 Scalability and performance

The first engineering blocker is Python-loop employee row scoping. Replace it with a reusable set-based database scope
using an agreed manager hierarchy, closure table or recursive query. Scope membership must be invalidated when manager,
employment-version or role data changes.

In parallel:

- remove full-list frontend materialisation;
- add indexes from measured query plans;
- budget queries for dashboards and high-volume endpoints;
- move large exports and expensive reports to resumable background jobs;
- paginate audit and notification feeds;
- test concurrent use, not only single-request latency; and
- publish tested workforce, transaction and document-volume envelopes.

**Required evidence.** Repeatable tests at 1,000 and 10,000 employees plus expected peak concurrency; p50/p95/p99 API
latency; database query counts; browser responsiveness; job completion and failure recovery.

### 6.2 Identity and access lifecycle

- implement Entra/OIDC with issuer, audience, nonce, state and PKCE validation;
- map controlled groups or claims to application roles without granting row scope implicitly;
- automate joiner, mover and leaver effects;
- prove prompt role removal and account disablement;
- enforce MFA/step-up rules through production identity context;
- provide monitored break-glass accounts with time-limited use;
- conduct periodic access reviews and segregation-of-duties checks; and
- distinguish system administration from HR data administration.

### 6.3 Data governance and privacy

- publish the field-level system-of-record matrix;
- maintain data ownership, classification, lawful purpose and retention metadata;
- minimise API responses by persona and task;
- support correction, restriction, export and deletion decisions consistently;
- add legal-hold overrides with accountable approval;
- test backup and replica treatment during deletion or restriction;
- prevent sensitive values from entering logs, traces, analytics or notification previews; and
- complete DPIAs for biometrics, employee relations, accommodation and predictive analytics.

### 6.4 Secure delivery and deployment

- build backend and frontend images once per release;
- run dependency, secret, static and container scans;
- generate SBOMs and provenance;
- sign immutable image digests;
- promote the same artifacts through protected environments;
- run migrations as a controlled one-shot task;
- record deployment, schema and configuration versions;
- define backward-compatible deployment and rollback rules; and
- require approval based on risk and evidence rather than branch name alone.

### 6.5 Reliability, recovery and observability

- define service-level objectives plus RPO and RTO;
- automate encrypted database and media backups with off-host retention;
- perform timed isolated restore rehearsals;
- verify hashes and accessibility of recent signed artifacts after restore;
- instrument API latency, error rate, queue age, task failure, notification delivery, sync freshness and storage;
- correlate requests, jobs and integrations without logging sensitive content;
- maintain runbooks and escalation ownership; and
- rehearse identity outage, payroll-sync failure, corrupted upload and failed migration scenarios.

### 6.6 Security assurance

- threat-model identity, documents, exports, cases, integrations and background tasks;
- add object-level authorization tests for every role and state transition;
- commission independent penetration testing before broad production use;
- test rate limits, file handling, malicious content, session controls and webhook replay;
- maintain vulnerability response and patch SLAs; and
- collect formal privacy, security and risk acceptance evidence.

### 6.7 Support, release and customer operations

Enterprise use requires an operating model as much as a codebase:

- named service owner, product owner, security owner and domain data owners;
- support tiers, hours, response targets and escalation paths;
- user administration and access-review procedures;
- release calendar, change communication and training;
- compatibility and deprecation policy;
- data-import and cutover playbooks;
- known-error and incident communication processes; and
- capacity and succession planning for the engineering/support team.

## 7. Fastest route to improvement

The order below maximises risk reduction and visible user value while avoiding feature work built on weak foundations.
Durations are indicative for a focused team and should be recalibrated after technical discovery.

### Phase 0 — Baseline and decisions (approximately 1 week)

1. Approve product position: South African HCM with external payroll and leave authorities.
2. Define personas, capability catalogue and system-of-record matrix.
3. Agree expected employee count, concurrency, availability, RPO and RTO.
4. Capture baseline task times, API latency, query counts and support pain points.
5. Assign business, legal, privacy, security and operational owners.

**Exit gate:** owners and decision records exist; performance and adoption targets are measurable; disputed system
boundaries are resolved.

### Phase 1 — Scale and dashboard correctness (approximately 2-4 weeks)

1. Replace Python-loop row scoping with a set-based employee-scope service.
2. Separate dashboard capabilities from row scope.
3. Move policy reads behind the cross-domain query seam.
4. Add all-role and multi-role dashboard authorization/browser tests.
5. Add representative query-count and latency tests.

**Why first:** this removes an enterprise-scale bottleneck and prevents misleading or unauthorised journeys across the
entire product.

**Exit gate:** scope query cost is bounded; every displayed dashboard action is permitted; representative load and role
tests pass.

### Phase 2 — High-volume UX and code reduction (approximately 3-6 weeks)

1. Replace `fetchAllPages` on the four highest-volume domains with server-side browsing.
2. Separate large export jobs from list views.
3. Split the largest pages into task-level panels and domain hooks.
4. Replace prompts/confirms and standardise form, error and loading behavior.
5. Finish generated-contract adoption for touched endpoints.
6. Consolidate upload validation and repeated actor/role queries.

**Exit gate:** representative 10,000-worker lists remain responsive; no touched feature imports handwritten transport
types; priority journeys pass keyboard and automated accessibility checks.

### Phase 3 — Identity and authoritative integrations (approximately 6-12 weeks)

1. Implement and test Entra/OIDC plus lifecycle disablement.
2. Build the shared idempotent sync-run, item-result, replay and reconciliation foundation.
3. Integrate employee/position/remuneration data with payroll.
4. Integrate leave balance and absence data.
5. Add operator freshness and exception dashboards.

**Exit gate:** production-like identity journeys pass; terminated and role-removed users lose access promptly; parallel
reconciliation meets agreed tolerance; failures are visible and replayable.

### Phase 4 — Production proof and accountable pilot (approximately 4-8 weeks, partly parallel)

1. Publish scanned, signed, immutable deployable artifacts.
2. Deploy through a protected target environment using the one-shot migration design.
3. Complete load, restore, security, privacy and accessibility evidence.
4. Run task-based UAT across all personas.
5. Establish monitoring, on-call ownership, support processes and release communication.
6. Run a controlled pilot with explicit success and rollback criteria.

**Exit gate:** the release-evidence pack contains actual results, not planned checks; critical UAT defects are closed or
formally accepted; restore and incident procedures have been rehearsed.

### Phase 5 — High-value product expansion (approximately 8-16 weeks per sensitive domain)

1. Implement the approved employee-relations case foundation.
2. Implement reasonable accommodation on its separately approved privacy model.
3. Add the HR service-delivery portal and knowledge layer.
4. Complete performance-improvement, benefit-reconciliation and learning-delivery lifecycles.
5. Add workforce-planning scenarios and governed analytics.

**Exit gate:** each domain has its own access, retention, privacy, migration, UAT and operational evidence. Feature count
alone is not an exit criterion.

## 8. Prioritised improvement register

| Priority | Improvement | Primary value | Dependency | Completion evidence |
|---|---|---|---|---|
| P0 | Set-based employee row scope | Scale, security consistency | Reporting-chain decision | Query/load tests |
| P0 | Capability-adaptive overview | Correct UX and least privilege | Capability catalogue | All-role browser tests |
| P0 | True server-side list browsing | Speed and usability | Stable filters/contracts | 10k dataset evidence |
| P0 | Entra identity lifecycle | Enterprise access control | Identity mapping | Joiner/mover/leaver tests |
| P0 | Payroll/leave reconciliation foundation | Data trust | System-of-record matrix | Parallel reconciliation |
| P0 | Immutable deployment and restore proof | Operational confidence | Target environment | Signed release and restore record |
| P1 | Accessibility and task-based UAT | Adoption and inclusion | Persona journeys | Manual and automated evidence |
| P1 | Generated contracts and shared UI patterns | Reliability and maintainability | API contract governance | Drift checks and removed duplicate types |
| P1 | Reporting catalogue and asynchronous exports | Decision support | Metric ownership | Reproducible governed reports |
| P1 | Employee-relations case foundation | Major coverage gap | Legal/privacy access matrix | Restricted end-to-end case test |
| P1 | HR service-delivery portal | Employee/HR efficiency | Routing and SLA design | Pilot service metrics |
| P1 | Reasonable accommodation | Compliance and inclusion | DPIA and disclosure rules | Privacy-approved workflow |
| P2 | Workforce planning | Strategic HR value | Trusted establishment/cost data | Approved scenario conversion |
| P2 | Learning/performance/benefit lifecycle depth | Product completeness | Existing domain cleanup | End-to-end domain journeys |
| P3 | Predictive or generative HR intelligence | Future differentiation | Quality, bias and governance gates | Controlled evaluation and human oversight |

## 9. Enterprise pilot go/no-go criteria

The system should not be described as enterprise-ready until all mandatory criteria have evidence:

- role, row and field access tests pass for every production persona and sensitive domain;
- SSO, MFA, disablement and break-glass behavior are proven in the target identity tenant;
- representative scale tests meet approved latency and error budgets;
- payroll and leave data show source, freshness and reconciliation state;
- production artifacts are scanned, signed, immutable and traceable to source;
- backup and media restore completes within approved RPO/RTO;
- monitoring and alert escalation have named responders;
- critical accessibility, privacy, security and UAT findings are closed or formally accepted;
- support, release, incident and data-correction procedures are staffed; and
- a pilot succeeds against task completion, data quality, adoption and support-volume targets.

## 10. Measures that should drive the programme

| Outcome | Suggested measure |
|---|---|
| Reliable access | Zero confirmed unauthorised object disclosures; timely access revocation |
| Scalable experience | p95 task/API targets at representative workforce and concurrency |
| Better usability | Journey completion, median completion time, error and abandonment rate |
| Data trust | Reconciliation match rate, exception age and source freshness |
| HR efficiency | Queue age, SLA attainment, manual handoffs and repeat contacts |
| Regulatory confidence | Evidence completeness, review age and accepted filings |
| Operational resilience | Availability, failed-job recovery, restore time and incident recurrence |
| Maintainability | Contract drift, change failure rate, cycle time and escaped defects |

Targets should be set from the Phase 0 baseline rather than invented without organisational context.

## 11. External comparison references

The competitive framing was checked against current official product descriptions:

- [Workday HCM](https://www.workday.com/en-us/products/human-capital-management/hcm-suite.html)
- [SAP SuccessFactors HCM](https://www.sap.com/products/hcm.html)
- [Oracle Fusion Cloud HCM](https://www.oracle.com/human-capital-management/human-resources/)
- [BambooHR platform](https://www.bamboohr.com/platform/)
- [Sage 300 People South Africa](https://www.sage.com/en-za/products/sage-300-people/)

Vendor descriptions establish advertised scope, not independently verified superiority. The recommended roadmap is
grounded primarily in the audited codebase and the evidence needed for this project's intended operating environment.

## 12. Immediate next action

Start Phase 1 as a bounded engineering tranche: set-based row scoping, capability-driven overview composition,
cross-domain query-seam cleanup, comprehensive persona tests and performance budgets. In parallel, product and
operations owners should complete the Phase 0 persona, system-of-record and service-level decisions so that identity and
integration work can proceed without rework.
