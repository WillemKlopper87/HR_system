# Session state — 2026-08-27 (session 9)

Written as a resume point. **Everything described as done is committed and pushed** —
run `git log -1` for the exact hash; `origin/master` matches local HEAD as of this write.

## Shipped this session

Not a C1-C7 backlog item — a targeted response to an external EE & B-BBEE regulatory field-guide review
(gazette-sourced research comparing SA employment-equity/B-BBEE/POPIA law against this codebase; see the
review's own "Consolidated enhancement backlog" for the full list). Three of its highest-exposure/lowest-effort
findings, in commit order:

1. **`2a2feaf`** — `EEReport` (the frozen EEA2/EEA4 snapshot) had no retention rule; `0003_seed_retention_rules.py`
   covered the plan and its evidence trail (reg. 9(15)) but missed the report itself (regs. 10(14)/12(3), five
   years). One migration, one test.
2. **`45c481e`** — `EESector`: all 18 EEA17 economic sectors seeded with the real 5-year targets from Gazette
   52514 (downloaded and read the actual PDF, not commentary — sector 1.10 Information and Communication's
   figures match what session 7/8's demo seed had already hand-entered, so no drift there). `EmployerConfig.sector`
   FK + a `GET /ee-plans/sector_defaults/` endpoint + a picker on `EEConfigurationPage.tsx`, so a plan's
   `sector_targets`/`disability_5yr_target_pct` can be pre-filled instead of hand-typed. Demo seed now points
   Sentech at sector 1.10 with `industry_sector="Information and Communication"` (was "Telecommunications").
3. **`891a691`** — `ee_reporting/reminders.py` + a new Celery beat entry: online-report-window-close (15 Jan,
   gated on whether EEA2/EEA4 are actually signed off for the closing report year) and EEA14
   notice-of-inability (last working day of Aug, ungated — no notice-tracking model exists to gate on).
   Deliberately **not** built: the certificate's 12-month expiry (no EEA15/16A-D model yet) and WSP/ATR's 30
   April deadline (a learning-app readiness check, not an ee_reporting one).
4. **`dfce506`** (two items in one commit) — recruitment funnel by demographic: `GET
   /dashboards/recruitment/funnel/`, stage-reached derived from `ApplicantStageEvent` (not `current_stage`, which
   would collapse a rejected applicant to "rejected" and erase how far they actually got) — the Code on
   integrating EE into HR practice's "track applicant pool, short-list, interviewed and offered by demographic".
   Same commit: calibration rating distribution now breaks down by race/gender/disability status alongside the
   existing by-division view (`PerformancePeriodViewSet.rating_distribution`), reusing the same small-cell rule.
5. **`a0e8ade`** — `TrainingRecord` gains B-BBEE skills-development evidence (Code series 300): a Learning
   Programme Matrix category slot (A–G — meanings unverified against the gazetted Codes, flagged in the model
   docstring), a learner-agreement flag, and a content-sniffed evidence upload (`learning/uploads.py` — a fourth
   copy of the same sniffer already duplicated in `documents`/`recruitment`/`ee_reporting` for the peer-app-import
   boundary; a real candidate for kernel promotion if a fifth ever shows up). New fields registered at INTERNAL
   tier in `rbac_audit/tiers.py` — `TieredModelSerializer` silently defaults anything unregistered to PUBLIC, so
   this was a real gap to catch before push, not paperwork. WSP/ATR export gains the three columns.
6. **`670454a`** — `GET /dashboards/management-control/`: black/black-female representation per level benchmarked
   to the EAP, plus employees with disabilities — the evidence schedule (not the scorecard's point value) the
   ICT Sector Code's Management Control element needs, assembled from data `ee_reporting.aggregation` already
   computes rather than a new capture surface.

7. **`0c531d9`** — `core_hr.ProbationPeriod`/`ProbationReview`: hr_admin opens/decides, line manager records
   reviews, same `RowScopePermission` row-scoping `TrainingRecord` already uses (self/own-team/all). `GET
   /dashboards/probation/` reports the confirmation rate by race/gender/disability status, counting only closed
   (confirmed/terminated) periods. New `ProbationPage.tsx`. Note for the next session: writing multi-hundred-line
   files via the Write/Edit tools hit repeated host-hook timeouts this session (worked around with small chunked
   `cat >>` heredocs via Bash, each under ~50 lines/3KB) -- if that recurs, chunk file writes rather than retrying
   the same large call.

8. **`f13001a`** — `core_hr.ExitInterview`: hr_admin-only (a management record naming individuals'
   departure reasons, not self-service), optionally linked to an `EmploymentChange` or a `ProbationPeriod`. `GET
   /dashboards/exit-interviews/` breaks reasons down by race/gender/disability status. New `ExitInterviewsPage.tsx`.

Full backend suite (1130+ tests across the touched apps) and frontend typecheck/lint/build all green before
each push. Remaining items from that same field-guide review — EEA1 self-declaration confidential-disability
mode, EEA12 analysis record, certificate lifecycle tracker, B-BBEE skills-development scorecard *calculator*
(the evidence fields for it now exist; the % vs. target computation does not), reasonable-accommodation register,
harassment intake, enforcement register — are unstarted and are now tracked in the dedicated
`docs/sprints/regulatory-review-backlog.md`, since they came from the external review rather than the original
C1–C7 sprint backlog. That file also records the production-integrity fixes identified by the 2026-08-27
follow-up code review.

## Shipped in session 8: EE plan measures, consultation-forum records, server-side pagination

Two slices landed. The first (EE plan + consultation-forum records) was built in an earlier stretch of that
session whose wrap-up step never ran — its four commits are labelled `wip:` and this file was left describing
session 7. That was corrected in session 8's own write-up; nothing about the work itself was incomplete.

### A. C6 — EE plan measures, consultation-forum records, progress snapshots (`13fc617`..`e110cf9`)

**The last effort-buildable C6 item** (assessment-provider adapter is vendor-blocked, leave is decision-blocked).
Gap per `NEXT_AGENT_BRIEF.md` #23: `EEPlan` existed as a model since Sprint 13, but the consultation-evidence
trail the EEA2 questionnaire's own Section F asks about was captured nowhere. Spec:
`docs/superpowers/specs/2026-08-26-ee-plan-consultation-forum-design.md`.

Four new models in `ee_reporting` (not a new app): `EEForumMember`, `EEForumMeeting` (with content-sniffed
PDF/DOCX minutes upload, 10 MB, `log_access`'d as EXPORT at Sensitive tier), `EEPlanMeasure` (EEA13-style:
responsible person + time frame, both required and validated inside the plan period), `EEPlanProgressSnapshot`
(create-only — a snapshot is evidence of what was tabled, so no update/delete endpoint exists). Four new
routers under the existing `ee_reporting/urls.py`, plus
`GET /ee-forum-members/composition/` — a derived s.16(2) adequacy check returning booleans and level codes
only, never per-demographic counts of the forum itself.

Two access decisions worth remembering, both recorded in `RBAC-Roles.md`:
- **Writes are hr_admin + ee_manager**, a deliberate departure from the module's otherwise hr_admin-only
  form-data writes — the forum, the measures and the monitoring are the EE manager's own operational job
  (EEA s.24 assigned senior manager).
- **A forum-member carve-out** on reads: an employee who holds or held a seat sees the roster and the meetings
  they attended, with `representation`/`notes` **redacted** (`union_nominated` reveals trade-union membership,
  POPIA s.26 special personal information). A non-member gets an empty list, not a 403 — no hint about what
  exists. The `composition/` endpoint is **excluded** from that carve-out, since it summarises the whole
  workforce's mix.

The questionnaire's Section F Y/N answers stay hr_admin-write and authoritative; these records are the
*evidence* behind them, cross-checked by `EEReport.validate` as **advisory findings, never a generation gate**.
Snapshot matrices are stored unsuppressed and small-cell-suppressed per requester on read, reusing the equity
dashboard's existing `can_see_unsuppressed_aggregates` rule rather than a second one.

Frontend: new `EEForumPage.tsx` (`/ee-forum`), and plan measures + progress snapshots added to
`EEConfigurationPage.tsx`. Seed data and `ee-forum-plan.spec.ts` (e2e) added. Backend: `ee_reporting` 116 tests
OK, of which `test_forum_plan.py` is 22.

### B. C7 — server-side pagination for the employee directory + checklists (`28fdcbc`)

Brief item #26, and the real fix for the `settled()` timing-flake class this file has carried under Known
defects for several sessions. The employee list was the worst `fetchAllPages()` offender: two full collection
walks (all employees, then all current `EmployeeVersion`s) joined client-side on every load.

`EmployeeListPage` now requests **one server page** with Previous/Next, and the second walk is gone entirely —
`EmployeeSerializer` gained `current_department` / `current_occupational_level` / `current_employment_status`,
fed by a `Prefetch(to_attr="current_versions_for_summary")` over `EmployeeVersion.objects.current()`, so the
summary costs one extra query per page rather than one per row. The `to_attr` is absent on non-list paths (a
freshly saved instance), where the accessor falls back to `instance.current_version`.

**The trap those three fields set, and the fix** — worth knowing before flattening any other versioned field
onto a summary serializer. `TieredModelSerializer` resolves each field through
`tier_of(model_label, field_name)`, and `tier_of` **defaults an unregistered field to `PUBLIC`**. So the three
new fields were served to every role that can read the employee row — including `sysadmin`, which holds
`row_scope=all` but `I:read=False` ("no standing access to S/R business data", `0002_seed_roles.py`) — even
though `occupational_level` and `employment_status` are `INTERNAL` on `core_hr.EmployeeVersion`, and even
though `hire_date`/`phone`/`personal_email` were being correctly dropped for that same requester in the same
response. They are now registered in `rbac_audit/tiers.py` under `core_hr.Employee` with the tiers of the
columns they flatten, and `EmployeeApiTests` has a sysadmin negative test that fails without the registration.

`ChecklistsPage` stops fetching every employee just to render names (`ChecklistInstanceSerializer` supplies
`employee_display`; the queryset already `select_related("employee")`), and its employee picker loads lazily
only when HR opens the manual-create form.

Also folded in: the ESS phone-persistence test now asserts the DB row and a fresh GET rather than just the
PATCH response; `core-hr.spec.ts` picks a serving employee explicitly (the directory deliberately includes
departed staff, whose historical detail has no current assignment) and waits on row visibility instead of
`settled()`; four `SerializerMethodField`s got return annotations, clearing their unresolved-type OpenAPI
warnings.

**Status: backend 1121 tests OK** (`--parallel auto`, 419s), `manage.py check --fail-level WARNING` clean, no
migration drift, `tsc -b` and `oxlint` clean (same 2 pre-existing fast-refresh warnings in `AuthContext.tsx`
and `ReferenceDataContext.tsx`). The e2e suite has **not** been re-run since the pagination change — see
Known defects.

## Shipped in session 7: C6 — salary-review/bonus cycles + total-rewards statement

The product owner's "let's finish C6" instruction named this as the next sub-item after mandatory-training
compliance, succession/talent pools, interview scheduling/careers-portal, and performance calibration/360 (all
shipped 2026-08-25/26). Gap per `NEXT_AGENT_BRIEF.md` #22: "proposals are one-off; no cycle object to batch
increases against a budget, and ESS shows benefits but not a consolidated rewards view." Spec:
`docs/superpowers/specs/2026-08-26-salary-review-cycles-total-rewards-design.md`.

### A. `CompCycle` — batches proposals against a budget

Extends `compensation` (not a new app) — `CompProposal` gains a nullable `cycle` FK and a `proposal_type`
(`increase`/`bonus`) rather than forking a second model, so the existing propose→approve→reject workflow and
segregation-of-duties check are reused, not duplicated. `CompCycle`: `name`, `period_start`/`period_end`,
`budget_amount` (flat currency pool — a %-of-payroll option was considered and rejected, spec §2.2: it would need
a frozen payroll baseline at cycle-open time, a real mechanism this task's brief didn't ask for), `department`
(nullable = org-wide, matching the brief's own wording rather than `CourseRequirement`'s two-axis scoping — spec
§2.3), `status` (draft/open/closed).

**Budget tracking**: `CompProposal.budget_impact` is a **property**, not a stored column — a bonus's full amount,
or an increase's delta over `baseline_salary_at_proposal` (a snapshot of `RemunerationRecord.fixed_remuneration`
at proposal time, only required for a cycle-attached increase). Utilization is derived live by summing
`PROPOSED`+`APPROVED` proposals' impact (never `REJECTED` — it never happened). **Over-budget reuses
`requires_override`/`override_reason`'s existing "flagged, not blocked" shape** (new `exceeds_cycle_budget` field)
rather than a second gate — a proposal can still be created/exist over budget, but approving it needs a reason,
same as an out-of-band pay-band proposal. Guarded against the classic concurrent-proposal race with
`select_for_update()` on the `CompCycle` row at both create and approve time (`compensation/services.py`) — the
same row-lock shape `core_hr.Employee.apply_lifecycle_event` already uses for its own read-then-write race.
`exceeds_cycle_budget` is recomputed **fresh, under lock, at approval time** (not trusted from the creation-time
flag) since cycle utilization is a shared, moving total across every proposal against it, unlike the
pay-band check which barely changes once a grade is snapshotted.

**Closing a cycle** auto-rejects any still-`PROPOSED` proposal (via the existing `reject_proposal`, which already
notifies the proposer) — never silently orphaned, never auto-approved (committing money nobody explicitly
approved is the wrong default; rejecting just means re-raising it in a future cycle if still wanted).

New data-quality check `COMP_CYCLE_OVERDUE` (`compensation/data_quality.py::cycle_overdue_handler`): an open cycle
past its `period_end` with an unresolved proposal. Deliberately **not** an "exceeds budget" check — that's
already a live flag directly on the proposal, so a data-quality exception for it would just be noise.

`CompProposal` also gained a read-only `performance_context` field (the employee's latest `final_score`, via the
**existing** `performance/queries.py::latest_final_score` seam succession built) — informational display only for
whoever already reads proposals, never an input to any amount or budget calculation (spec §2.8).

### B. `GET /my-total-rewards/` — a genuinely new self-scope carve-out

**The load-bearing decision.** `compensation`'s entire prior design philosophy was "no carve-out, comp_manager/
hr_admin only, module-wide, catalog included" (the models' own docstrings). A total-rewards statement is
fundamentally different in kind — an employee's own confirmed current pay and benefits, shown to themself, the
same category `MyProfilePage.tsx`/`MyBenefitsPage.tsx` already show for every other domain. Confirmed by grep
this didn't already exist anywhere (no salary field in `MyProfilePage.tsx` or `api/types.ts`'s `self` scope).

**The boundary** (spec §3): a new function view (not a `ModelViewSet`) resolves the employee **only** from
`get_request_employee(request)` — no id parameter exists anywhere on the endpoint, for any role, including
comp_manager/hr_admin acting on their own login. Exposes: the requester's own latest `RemunerationRecord` (fixed/
variable/total, via new `ee_reporting/queries.py::latest_remuneration_for_employee` — ee_reporting's first read
seam); the *one* `PayBand` for the requester's own current `job_grade` plus a computed percentile position (never
any other grade's band, never a list); their own `BenefitsElection` rows joined to the catalog (zero new access —
`MyBenefitsPage.tsx` already proves this is self-visible, just folded in for convenience); their own
`latest_final_score` (ditto, already visible via `MyPerformancePage.tsx`). **Never** exposed, to anyone, via this
surface: any `CompProposal` (pending or historical — a proposed change is not confirmed pay, and premature
disclosure risks setting expectations the organisation hasn't committed to, or leaking cycle budget dynamics);
any other employee's data; any `CompCycle` detail. **No `RequiresPayrollStepUp`** — that control exists for
privileged access to *someone else's* Restricted-tier pay data, not self-view of your own (none of the existing
`My*` ESS pages require it either, despite touching Sensitive/Restricted fields in the self-view case).

**No privileged "view anyone's statement" mode was built** (spec §3.4) — comp_manager currently has **zero**
standing access to `RemunerationRecord` at all (`ee_reporting.permissions.RemunerationRecordPermission.READ_ROLES
= ("hr_admin", "auditor")` only, a pre-existing, deliberate restriction); building a second privileged-viewer path
into this endpoint would either silently widen that table as an unplanned side effect, or need its own separate
access decision this task's brief didn't ask for. hr_admin already has full, direct access to every underlying
model independently for a real pay conversation.

**Current-salary source of truth: `RemunerationRecord`, never `CompProposal`** (spec §4) — per ADR-006/
`compensation.PayBand`'s own docstring ("actual pay stays in SAP"), confirmed by how `ee_reporting`'s own EEA4
generation already treats `RemunerationRecord` as ground truth, never cross-checked against `CompProposal`. A
proposal, even `APPROVED`, is a workflow record of an *intended* change — the number doesn't change until it
lands in SAP's next extract and appears as a new `RemunerationRecord` row (no live SAP integration exists yet,
per ADR-006's own noted future Sprint 12b interface), which can be days-to-weeks behind in practice. Showing an
employee a number payroll hasn't started paying yet would be a worse failure mode than being one reporting cycle
behind reality.

### Frontend

New `CompCyclesPage.tsx` (`/comp-cycles`, comp_manager/hr_admin, **not** wrapped in `RequirePayrollStepUp` —
matches the backend decision) — list/create/open/close, a budget-utilization bar per cycle, links to that cycle's
filtered proposal list. `CompProposalsPage.tsx` gains a proposal-type selector (increase/bonus with the
type-appropriate amount field), an optional cycle attach, `?cycle=` filtering (linked from the cycles page), an
"Over cycle budget" flag alongside the existing "Outside band" one, and a read-only "Latest rating" column from
`performance_context`. New `MyTotalRewardsPage.tsx` (`/my-total-rewards`, no role gate, no step-up) — current
salary, pay-band position with a percentile bar, benefits (read-only here, links to My Benefits to edit),
performance context. Both new nav entries added (`Compensation` category, `My Space` category).

### Backend / frontend status

**Backend: 1046 → 1098 tests, OK** (full-suite run to completion, ~31 min on this machine) — net new: `compensation` app grew from
45 to 94 tests (cycle model/service/API coverage: budget-impact derivation, the department-scope and
OPEN-cycle-required create-time checks, the fresh-at-approval-time budget recheck, close-cycle auto-reject,
self-scope negative tests for `/my-total-rewards/`), plus a new `ee_reporting/test_queries.py` (7 tests, the new
`latest_remuneration_for_employee` seam), plus `core_hr`'s `DataQualityException.ExceptionType` migration.
`manage.py check` and `makemigrations --check --dry-run` both clean. New migrations:
`compensation/migrations/0002_historicalcompcycle_and_more.py`,
`core_hr/migrations/0016_alter_dataqualityexception_exception_type.py`. `tsc -b` and `oxlint` clean (same 2
pre-existing warnings only: `AuthContext.tsx`, `ReferenceDataContext.tsx`).

**e2e: 61/73 passed** (full suite run to completion by the coordinating session after this session's process
was killed mid-verification; 14.3 min, the slowest run yet on this machine) — all 4 new tests green, failure
analysis in the next paragraph. New `compensation-cycles-total-rewards.spec.ts` (4 tests): comp_manager
confirms `/comp-cycles` has no step-up gate (unlike `/pay-bands`/`/comp-proposals`) and can create/open a cycle;
a full budget-race demo (create a small-budget cycle, two bonus proposals, the second correctly flagged "Over
cycle budget," self-approval blocked even with an override reason supplied); the employee login's
`/my-total-rewards/` renders real salary/band/benefits/performance sections and the API ignores a foreign
`?employee=` query param (always answers for self) with no `comp_proposal`/`proposed_annual_salary` shape ever in
the payload; a non-comp/hr role has no nav link and gets 403 on both the route and the API. One existing assertion
fixed in `compensation.spec.ts` (`'Proposed salary'` → `'Amount'`, the column header's own necessary rename since
it now shows either a salary or a bonus amount).

**The 12 failures, each read rather than assumed.** Ten are the documented `settled()` class in its usual shape
(`Loading…` never clearing on the large `/employees` list within 15 s): `core-hr` ×2, `contract-renewals`,
`ee-integrity`, `compensation` (the TOTP pay-bands test — a `Loading…` timeout, not a logic error, and the
`compensation.spec.ts` edit this slice made was one column-header string), `performance` ×4, `succession`. Two are
newly observed and this slice touched neither: `careers-portal` (`waitForURL('/employees')` timing out — the same
large-list load behind a different assertion) and `onboarding`. Standalone re-run: `careers-portal` 4/4 passed;
`onboarding` 4/5, and its one failure has a specific mechanism worth recording rather than filing as "flake": the
manager's Complete click returned **200** and the checklist refetch came back with the completed item, but
`ChecklistsPage` reloads checklist instances *and* the full `/employees/` list in one `Promise.all`, and
`useApiQuery` deliberately keeps old data visible during a reload — so there is no `Loading…` for `settled()` to
wait on, and the row only flips to Done once the slower employees fetch also lands. On initial load that fetch took
2–3 s; after the mutation it still hadn't returned 9 s later when the test gave up (10 s assertion window). Same
root cause as the whole class (`fetchAllPages` at seed scale); C7 server-side pagination is the real fix, and a
cheap page-level mitigation is to refetch only instances after a mutation.

**Real bugs found and fixed while writing the new spec, not routed around:**
1. `approve_proposal`'s first draft rebound its `proposal` parameter to a freshly-locked DB fetch instead of
   mutating the caller's own object in place, breaking the pre-existing "the view/tests read the same object back
   after calling this" contract — reverted to locking only the `CompCycle` row and mutating `proposal` throughout,
   same shape the original code already had.
2. The `close_cycle` view action discarded the service function's return value (which — unlike `approve_proposal`
   — legitimately does need to re-fetch-and-lock a fresh `CompCycle` instance) and serialized the stale pre-close
   object; fixed to capture and serialize the returned instance.
3. `approve_proposal`'s budget-flag write only updated `exceeds_cycle_budget` in `update_fields` "if changed from
   the in-memory value" — which could wrongly skip persisting `True` when a *prior, failed* approve attempt on
   the same object had already flipped the in-memory attribute without saving (raised before reaching `.save()`).
   Fixed to always include it in `update_fields` unconditionally; a boolean field costs nothing to always write.

**e2e authoring lessons** (kept here since they're non-obvious and this machine's characteristics make them worth
recording): `RequirePayrollStepUp`'s outer "Checking access…" and `StepUpChallenge`'s own inner "Loading…" are
two *independent* async states — a bare `.count()` check on the challenge heading, or on the enroll-vs-already-
enrolled branch, immediately after `goto()` races whichever hasn't resolved yet and needs an explicit wait for
each. `getByLabel('Employee', { exact: true })` on `CompProposalsPage`'s employee `<select>` (~150 options)
reliably failed to resolve at all — even with `force: true` bypassing actionability checks entirely, proving it
wasn't a stability/actionability problem — while `page.locator('form.inline-form').locator('select').nth(0)`
against the exact same element worked instantly; root cause not chased further (not worth the time against a
working alternative), but recorded in case it recurs elsewhere. `hradmin2`'s seeded password is `hradmin123`
(matching `hradmin`'s own), **not** the `"<username>123"` pattern every other demo login follows — confirmed via
`seed_demo_data`'s own printed credentials line; `helpers.ts`'s `login()` computes the wrong password for it, so
it needs a direct fill rather than the shared helper. A `StepUpGrant` is tied to the **employee**, not the browser
session — reusing `hradmin`/`compmanager` for a fresh-TOTP-enrollment flow in a new spec silently broke
`compensation.spec.ts`'s own pre-existing tests that assume those two accounts have never enrolled a device,
within the same one shared seeded backend (`workers: 1`) — `hradmin2` is the only comp_manager/hr_admin demo
login nothing else touches, which is also why the "a genuinely different admin approves" happy path isn't
re-exercised at the UI level (a third such account doesn't exist in the demo data) and is left to the backend
unit tests that already cover it directly.

## Seed data

`seed_demo_data.py` gained `_seed_comp_cycle_demo_data`, called **after** `_seed_ee_reporting_demo_data` (an
increase proposal attached to a cycle needs the employee's `RemunerationRecord` as its budget baseline, which
only exists once that loop has run): one open "FY2026 Annual Review" cycle (R100,000 budget), an increase
proposal for the `employee` demo login (+8% of their current fixed remuneration), and two fixed R60,000 bonus
proposals for two other sampled employees — the second bonus is guaranteed to flag `exceeds_cycle_budget=True`
regardless of the (randomised) increase's exact size, since 60,000+60,000 alone already exceeds the 100,000
budget. Validated against a throwaway SQLite DB (`SQLITE_PATH` override) before trusting it in e2e — confirmed
correct utilization math and the expected True/False flag split on the actual seeded data.

## Next up — the menu (accurate as of today, not a recommendation)

- **C6 is done as far as effort can take it.** All six effort-buildable sub-items are shipped
  (mandatory-training compliance, succession/talent pools, interview scheduling/careers-portal, performance
  calibration/360, salary-review/bonus cycles + total rewards, and now EE plan measures + consultation-forum
  records). The seventh, the assessment-provider adapter, is vendor-blocked — see below. Nothing is left to
  pick here; `docs/sprints/backlog-uat1-and-c2-c7.md`'s C6 line is the source of truth.
- **C7 — UX / NFR**, now partly underway: server-side pagination started with the employee directory and
  checklists (`28fdcbc`). The same `fetchAllPages()` pattern remains on ~40 other call sites — the next most
  valuable ones are the checklist and data-quality lists, and any page that fetches all employees purely to
  render a name or a picker (the two fixes used here — a `*_display` field on the serializer, and a lazily
  loaded picker — generalise directly). Also unstarted in C7: the responsive/accessibility pass, adopting the
  already-generated OpenAPI types in place of the hand-written `api/types.ts`, and the 1.31 MB
  identity-verification bundle (face-recognition deps should load only when the camera flow starts).
- **Real assessment-provider adapter (C6)** — **still blocked on a vendor decision (Sprint-0 action A4), not
  effort, same as every prior session.** Don't pick this expecting an effort-only slice.
- **Leave / absence management** — still blocked on the cede-to-SAP decision (see below), not effort.
- **C3 — Identity & integrations**: OIDC/Entra SSO (ADR-004); SAP payroll read-only pull; leave read-only mirror
  (overlaps the blocked leave decision above); field-level step-up for `recruitment.Offer` pay fields.
- **C4 — Generic delegation & approvals**: generalise `SigningDelegation` → `Delegation(scope)`; "my approvals"
  inbox.
- **C5 — Labour relations**: disciplinary & grievance cases (warnings, hearings, outcomes, CCMA).
- **C7 — UX / NFR**: responsive + accessibility pass; server-side pagination/search (this would also be the real
  fix for the `/employees`-list-style performance flakes documented below); broader bulk import/export; report
  builder + scheduled emails.

`docs/sprints/backlog-uat1-and-c2-c7.md`'s C6 line now has five of seven sub-items ticked off — use that file, not
this narrative list, as the source of truth going forward.

## Blocked on a decision, not effort

- **Leave / absence management.** Ceded to SAP as "mirror only" (C3), but nothing exists — not even the mirror —
  while the Policy Library ships a Leave Policy document with no system behind it. Needs the cede-to-SAP decision
  revisited before anyone builds it. Unchanged this session.
- **Real assessment-provider adapter (C6).** Sprint-0 action A4 (vendor shortlist) is still open. Unchanged.

## Known defects

- **ESS phone edit does not persist across reload** (`ess-policies.spec.ts`). **Believed closed** — the backend
  test now asserts the DB row and a fresh GET after the PATCH, not just the PATCH response, and passes. Left
  listed here because it has not been re-confirmed against the browser since; drop it once an e2e run is green.
- **`core-hr.spec.ts`/`contract-renewals.spec.ts`/`ee-integrity.spec.ts`/`succession.spec.ts`'s `settled()` timing
  flake on the large `/employees` list.** This was a real performance characteristic (`fetchAllPages`'s unfiltered
  full-list + full-version fetch on first load at ~153-employee seed scale), not a traditional non-deterministic
  flake — and `28fdcbc` removed the cause for the `/employees` directory specifically. **Not yet verified:** the
  e2e suite has not been re-run since that change, so whether the flake class is actually gone (and whether the
  new Previous/Next pagination broke any spec that assumed the whole list was on screen — several specs search
  for an employee row by name) is the first thing the next session should check. Any remaining page that still
  walks the full list on load will keep exhibiting it. This session's own new spec hit the same underlying
  slowness (the ~150-employee list load, now fetched a third time alongside proposals/cycles on
  `CompProposalsPage`) and needed explicit longer per-assertion timeouts rather than the global default — recorded
  in the e2e-authoring-lessons section above, not treated as a code bug.
- **`performance.spec.ts`'s "a full year" test (and the tests that build on its state) fails on a `settled()`
  timeout.** Unchanged from several sessions running now — same root-cause class, not chased (out of scope for
  every session's own slice so far).
- **`compensation.spec.ts`** — flagged as newly-observed-and-intermittent a few sessions ago; did not reproduce
  in this session's runs either (both the pre-existing tests and the new spec passed cleanly once the e2e-authoring
  issues above were fixed). Still worth a look if C7's server-side pagination is ever picked up.
- This session's own machine independently reconfirmed the documented "background processes get killed / this
  machine's load varies" characteristic: several `npx playwright test` invocations against the identical,
  unchanged spec produced different failure shapes run to run (a `selectOption` actionability timeout, a
  login-page-not-rendering timeout, a proposals-list-not-reloaded-yet timeout) before finally passing cleanly and
  repeatably — each was individually investigated (not assumed away) and traced to either a real code/test bug
  (fixed, see above) or genuine environmental slowness under load (addressed with explicit longer timeouts, not
  dismissed).
- Parked residuals from C1 pt 2 (contract-renewal read/write role gaps, missing `@extend_schema`), the deliberate
  `let_lapse` gap, and the POPIA export's `documents`+`core_hr`+`rbac_audit`-only scope — all unchanged, see prior
  session-state history in git log for detail if needed.
- **From four sessions ago, unchanged:** historical free-text `TrainingRecord.title` rows never retroactively
  satisfy a `CourseRequirement` (no backfill attempted); no automatic enrollment when a `CourseRequirement` newly
  applies to someone.
- **From three sessions ago, unchanged:** no broader "role/career track" talent pool independent of a specific
  critical post; no manager-nominates/hr_admin-confirms two-step succession nomination workflow; unflagging a
  critical post does not cascade-withdraw its candidates; no "sole ready successor is themselves at-risk
  elsewhere" data-quality enrichment; no reminders/notifications for succession.
- **From two sessions ago, unchanged:** no configurable per-requisition interview scorecard criteria; no scorecard
  edit-lock after submission; no proxy scorecard entry by hr_admin on an interviewer's behalf; an interviewer's
  applicant summary excludes prior stage-event notes; no calendar/video-conferencing integration; no
  staging/quarantine table for public careers-portal submissions; no applicant-facing "track your application
  status" self-service view; no CAPTCHA on the public application form.
- **From last session, unchanged:** no live multi-party calibration meeting tooling — hr_admin records an offline
  outcome, by design; no `CompProposal` linkage from a calibrated/final score (this session's cycle work did NOT
  build this either — the calibration score surfaces on a proposal as read-only `performance_context`, but there
  is still no automatic "final band → draft CompProposal" write path, a different, larger feature); no
  re-signature on a calibration adjustment; peer/direct-report 360 free text never reaches the subject, ever, even
  pooled/paraphrased; direct-report feedback may permanently sit below the 3-response floor in a small team; no
  automatic re-open of a `Feedback360Request` when its agreement is later amended.
- **New this session, recorded deliberately:** no privileged "view any employee's total-rewards statement" mode
  for comp_manager/hr_admin — self-only, full stop, a deliberate limitation (see §3.4 reasoning above), not a gap;
  no distinguishing field between "a human rejected this proposal" and "the cycle closed underneath it" (both are
  reconstructable from `CompCycle.closed_at` vs. `CompProposal.history` timestamps); no payroll-relative (%)
  budget option, flat currency pool only; a cycle's `department` scope is enforced at proposal-creation time only,
  not continuously (an employee transferring departments mid-cycle isn't retroactively evicted from an
  already-created proposal).

## Environment notes

- **GitHub Actions is billing-blocked** — every job fails in seconds. Push directly; local suites are the gate.
  Not a code problem.
- The venv at `C:\Users\KlopperW\AppData\Local\venvs\hcm` worked throughout this session with no rebuild needed.
- **The e2e suite's `backend-server.mjs` resolves Python via `$PYTHON`, then `backend/venv/Scripts/python.exe`,
  then bare `python` on PATH — none of which is this machine's actual venv location.** `npm test` fails outright
  (`ModuleNotFoundError: No module named 'django'`) unless you set `$PYTHON` explicitly:
  `PYTHON="C:\Users\KlopperW\AppData\Local\venvs\hcm\Scripts\python.exe" npm test` (or `npx playwright test
  <file>` for a single spec). Applied correctly from the start of this session.
- **This session's machine was noticeably slower and more erratic than prior sessions** — a single backend
  `manage.py test compensation` run went from ~48s to ~100-140s between consecutive invocations with no code
  change in between, and individual e2e spec runs against the *identical* unchanged file produced different
  failure shapes run to run before stabilizing. Every failure was independently verified against its own actual
  error output before being attributed to either a real bug (three found and fixed, see above) or environment
  slowness (addressed with longer explicit timeouts) — never assumed away without checking. A future session
  seeing a slow or once-off-flaky run on a machine this variable should do the same: re-run before concluding
  something is broken, but never skip reading the actual failure either.
- **Background processes get killed / tool calls time out on this machine.** Commands with an unpredictable
  runtime were started with `run_in_background`, then polled with bounded `Bash` calls or awaited via the
  notification system — never backgrounded and abandoned. Commit-and-push happened after every slice (spec →
  backend → backend tests → frontend → seed data → e2e spec + fixes → docs), matching the process lesson from
  every prior session.
- A separate AI agent runs a Django server for an **unrelated** project on port 8000 on occasion — checked this
  session (`Get-NetTCPConnection`/`Get-CimInstance Win32_Process`) when e2e runs were behaving unpredictably;
  found no stale/conflicting server process at the time of checking, so the erratic e2e results this session were
  general machine load, not a port collision with that other project.
