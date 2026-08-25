# Session state — 2026-08-25 (session 3)

Written as a resume point. **Everything described as done is committed and pushed** —
`origin/master` is current.

## Where the work is

Last code change: `15d7aa0` (e2e bug fixes). This doc update is the final commit of the session, pushed
immediately after — run `git log -1` for the exact hash. Working tree clean.

## Shipped today: C6 — mandatory-training compliance

The product owner explicitly deferred the still-blocked leave/absence decision (see below) and picked C6's
mandatory-training-compliance sub-item as the next demand-driven pick, per `ROADMAP-2026-08.md`/
`NEXT_AGENT_BRIEF.md` §7.3 #21. Spec: `docs/superpowers/specs/2026-08-25-mandatory-training-compliance-design.md`.

**What it is:** extends the existing `learning` app (no new app) with a `Course` catalogue and
`CourseRequirement` scoping rules, wires `TrainingRecord.course` (nullable FK, no backfill onto historical
rows) into the catalogue, and adds a derive-on-read compliance-status engine plus a completion-rate dashboard
and a row-scoped overdue-individuals list.

**Scoping FK choice for `CourseRequirement` (department/occupational_level, both optional):** investigated all
of `EmployeeVersion`'s structured fields per the brief's own steer, not assumed. `job_title` was rejected —
free text, the exact reliability problem this feature exists to fix, applied to a different field. `Position`
was rejected — an individually-numbered post (persists across incumbents, keyed by `post_number`), not a role
*type*; a rule like "all Senior Management" doesn't naturally express as a list of posts. `job_grade` was
considered and set aside — a pay-banding concept layered under `occupational_level`, not an independent
scoping axis any worked example in the brief actually needed. `Department` and `OccupationalLevel` won: both
already required fields on `EmployeeVersion`, already what `skills_inventory`'s existing by-department/by-level
breakdown groups by, and match the brief's own examples exactly ("all of Finance" = department only, "all
Senior Management" = level only, both = the intersection). Both left null on a rule means an organisation-wide
mandate (a POPIA/safety induction everyone must complete) — a real, common pattern, not a footgun to force
around. Full investigation: spec §2.3.

**Compliance is derived, never stored** — `learning/compliance.py`, no `ComplianceRecord` table, same
"derive, don't store" philosophy as `establishment.Position.current_occupant`. Given an employee (or queryset)
and an as-of date, it works out which requirements currently apply (matched against the employee's *current*
`EmployeeVersion`'s department/occupational_level), and whether a `TrainingRecord(course=X, status=completed)`
satisfies each one within its validity window (`Course.validity_days`, null = never expires). Status is
`compliant` / `due` / `overdue`; "subject since" is `max(requirement.effective_from, version.valid_from)` — the
later of "the rule existed" and "this employee has been in the version currently on record" — so a rule added
after people are already employed starts their clock at the rule's own date, per the brief's explicit
requirement, while someone transferring into newly-scoped territory starts at their transfer date.

**Row-scoping decision for the overdue-individuals dashboard:** the aggregate completion-rate rollup
(`GET /dashboards/learning/training-compliance/`, by course/department/occupational-level, no names in it) is
**hr_admin-only**, same gate and reasoning as the existing `skills_inventory` endpoint — Internal-tier subject
matter, already restricted, so small-cell suppression (which protects a *wider* audience from demographic
aggregates) has no audience to protect against here. The **named** overdue-individuals list
(`GET /dashboards/learning/training-compliance/overdue/`) is **row-scoped** using the existing
`rbac_audit.drf.row_scoped_queryset` primitive — exactly the same call shape `learning/views.py::
team_development` already uses (`row_scoped_queryset(Employee.objects.all(), employee, employee_field=None)`).
`line_manager` sees only their own reporting chain; `hr_admin`/`auditor`/other all-scope roles see everyone; a
base `employee` sees only themselves. **No new access-control mechanism was invented** for this — reusing the
existing primitive was itself the design decision (spec §5.4), directly satisfying the brief's "manager should
only see their own reports' overdue status, not the whole org" requirement.

**Data-quality registry entry:** `core_hr.models.DataQualityException.ExceptionType.MANDATORY_TRAINING_OVERDUE`
(new choice, migrated — same shape `PERFORMANCE_OVERDUE`/`COMP_PROPOSAL_STALE` used), registered from
`LearningConfig.ready()` via the existing `core_hr.data_quality.register()` seam; `learning/data_quality.py::
overdue_training_handler` reuses `compliance.py`'s own derivation rather than re-computing anything.

**Reminders:** a new daily Celery task (`learning/reminders.py` + `learning/tasks.py`, its own
`CELERY_BEAT_SCHEDULE` entry) reusing `notifications.services.notify`/`notify_many` — an employee is nudged
once at `MANDATORY_TRAINING_REMINDER_OFFSET_DAYS` (default 14, env-configurable) before their own due date;
their manager is nudged once, the day a requirement actually lapses into overdue (one event, not a repeated
daily nag — the dashboard/data-quality exception already surface the ongoing state). Mirrors
`core_hr/contract_reminders.py`'s exact-offset-day shape, not `performance/reminders.py`'s `ReminderLog`-deduped
range shape.

**A real bug the tests caught before it shipped:** `notifications.models.Notification.Kind` had no registered
choice for `mandatory_training_reminder` — Django doesn't validate `choices` on save, so this would have
written silently and broken `get_kind_display()`, the exact regression class
`core_hr/test_reminders.py::ContractReminderNotificationTests`'s own docstring warns about for
`contract_reminder`. Fixed by adding the choice (+ migration) before any test exercised it for real.

**Frontend:** `CourseCataloguePage.tsx` (hr_admin — Course + CourseRequirement CRUD, under Performance & Growth
nav), `TrainingCompliancePage.tsx` (hr_admin — the aggregate dashboard), and a new "Overdue mandatory training"
section appended to the existing `TeamDevelopmentPage.tsx` (row-scoped, same page every manager already uses
for their team's skills/certs/training rollup). `MyLearningPage.tsx`'s enrollment form gained an optional
catalogue-course picker that pre-fills title/provider — still editable, `title` stays the field actually stored
(ad-hoc requests keep working exactly as before, `course` stays null for them).

**Backend: 926 tests, OK** (up from 888) — `manage.py test`, `manage.py check`, and
`makemigrations --check --dry-run` all clean.

**e2e: 50/57 passed** on the full suite (`npm test`, ~8.7 min). All 6 new `learning-compliance.spec.ts` tests
and the one modified `talent.spec.ts` test are green. Getting there caught real bugs, fixed before the final
run (see `hcm/frontend/e2e/learning-compliance.spec.ts` and `talent.spec.ts` commit `15d7aa0` for detail):
1. `talent.spec.ts`'s `team-development` assertion used an unscoped `table thead` locator — a real regression
   this session's own change caused, since `TeamDevelopmentPage` now renders a second `<table>` (the new
   overdue-training section) and the locator started matching two elements. Fixed by scoping to
   `.locator('table').first()`.
2. `learning-compliance.spec.ts`'s own catalogue-page assertions had the same two-tables-share-text problem
   (a seeded requirement's "Course" column repeats the course name, so an unscoped `table tbody tr` matched
   rows in both the courses table and the requirements table). Fixed by scoping per table.
3. The row-scoped overdue-list assertion assumed exactly one matching row; because the seeded safety-induction
   requirement is department-scoped to the whole Engineering department (and nobody in seed data has completed
   it), the whole reporting chain shows up, not just one person. Fixed to assert on `.first()`.
4. `selectOption({ label: /regex/ })` isn't valid Playwright API (label must be an exact string) — fixed to the
   exact rendered option text.

The 7 remaining failures are pre-existing/environmental, not from this slice — verified, not assumed:
- `contract-renewals.spec.ts` ×1, `core-hr.spec.ts` ×2 — the pre-existing, already-documented `settled()`
  timing flake on the large (153-employee) `/employees` list (see "Known defects" below).
- `performance.spec.ts` ×4 — all four cascade from one `settled()` timeout inside the "a full year" test
  (`performance.spec.ts:283`, waiting on a page mid-flow). **Reproduced independently twice**, including with
  `performance.spec.ts` run completely alone (no other spec files in the same process) — rules out cross-file
  contention as the cause. `performance.spec.ts` contains zero references to `learning`/`course`/`training`
  anywhere, and this session touched no file it exercises. This is the same broad root-cause class as the
  documented `core-hr` flake (a page not settling within the timeout under current machine load) but a
  **different specific symptom than last session's note** ("one unrelated browser-session error... 'Protocol
  error... session closed'") and a higher failure count (4, not 1) — recorded honestly as newly observed today
  rather than silently folded into the old line item. Not chased, per this session's explicit brief (out of
  scope for a `learning`-app slice) — flagged in "Known defects" below for whoever next has spare capacity.

## Next up — the menu (accurate as of today, not a recommendation)

Sequencing note: the demoable-lifecycle sequence (`docs/MVP-Backlog.md` Part B) already closed four of its
five original breaks (onboarding, org chart, personal documents, offboarding); the fifth (leave/absence,
below) is still blocked on a decision, not effort — **that framing is unaffected by today's C6 work**, which
was an explicit demand-driven pick made *while* leave/absence sits blocked, per `NEXT_AGENT_BRIEF.md`'s own
"C3/C4/C5/C6/C7 by demand" sequencing. Nothing below is a recommendation for what's next — just an accurate
list of what remains open:

- **Leave / absence management** — still blocked on the cede-to-SAP decision (see below), not effort.
- **C6 — remaining talent-depth sub-items** (mandatory-training compliance is now done): succession/talent
  pools + career paths (on `Position`); recruitment interview scheduling + panel scorecards + external careers
  portal; performance calibration/moderation + 360; salary-review/bonus cycles + total-rewards statement; EE
  plan + consultation-forum records; real assessment-provider adapter.
- **C3 — Identity & integrations**: OIDC/Entra SSO (ADR-004); SAP payroll read-only pull; leave read-only
  mirror (overlaps the blocked leave decision above); field-level step-up for `recruitment.Offer` pay fields.
- **C4 — Generic delegation & approvals**: generalise `SigningDelegation` → `Delegation(scope)`; "my
  approvals" inbox.
- **C5 — Labour relations**: disciplinary & grievance cases (warnings, hearings, outcomes, CCMA).
- **C7 — UX / NFR**: responsive + accessibility pass; server-side pagination/search (this would also be the
  real fix for the `/employees` list performance flake below); broader bulk import/export; report builder +
  scheduled emails.

`docs/sprints/backlog-uat1-and-c2-c7.md`'s C6 line has been split into individually-checkable sub-items with
mandatory-training compliance ticked off — use that file, not this narrative list, as the source of truth
going forward.

## Blocked on a decision, not effort

- **Leave / absence management.** Ceded to SAP as "mirror only" (C3), but nothing exists — not even the
  mirror — while the Policy Library ships a Leave Policy document with no system behind it. Needs the
  cede-to-SAP decision revisited before anyone builds it. Unchanged this session.

## Known defects

- **ESS phone edit does not persist across reload** (`ess-policies.spec.ts`). Real, reproduced at base
  commit, Sprint-15 territory. Unchanged.
- **`core-hr.spec.ts`/`contract-renewals.spec.ts` `settled()` timing flake on the large `/employees` list.**
  Unchanged — still a real performance characteristic (`fetchAllPages`'s unfiltered full-list + full-version
  fetch on first load at ~153-employee seed scale), not a traditional non-deterministic flake. Server-side
  pagination (C7) is the real fix.
- **New this session: `performance.spec.ts`'s "a full year" test (and the 3 tests that build on its state)
  now fails on a `settled()` timeout at line 283**, reproduced twice including standalone — same root-cause
  *class* as the item above (a page not settling under current machine load within the timeout), landing on a
  different, heavier multi-step test this time. Verified unrelated to this session's `learning`-only changes
  (the spec file has zero references to anything this slice touched). Worth a look if a future session has
  spare capacity and this keeps reproducing — either the same server-side-pagination-style fix, or (if it
  turns out to be genuinely `performance`-module-specific rather than general page weight) something in that
  module's own heavy nested-serializer payload.
- Parked residuals from C1 pt 2 (contract-renewal read/write role gaps, missing `@extend_schema`), the
  deliberate `let_lapse` gap, and the POPIA export's `documents`+`core_hr`+`rbac_audit`-only scope — all
  unchanged this session, see prior session-state history in git log for detail if needed.
- **New, recorded deliberately (this session):** historical free-text `TrainingRecord.title` rows never
  retroactively satisfy a `CourseRequirement` — no `course` backfill was attempted (no reliable title→course
  mapping to backfill safely; spec §2.5/§9). HR would need to re-file old records against the catalogue if that
  history needs to count.
- **New, recorded deliberately (this session):** no automatic enrollment when a `CourseRequirement` newly
  applies to someone (new rule, or a transfer into scope) — HR/the employee still create the `TrainingRecord`
  through the existing flow. No SETA-levy cost rollup either — this slice is the catalogue+compliance half of
  §7.3 #21, not the levy-tracking half (spec §9).

## Environment notes

- **GitHub Actions is billing-blocked** — every job fails in seconds. Push directly; local suites are the
  gate. Not a code problem.
- The venv at `C:\Users\KlopperW\AppData\Local\venvs\hcm` worked throughout this session with no rebuild
  needed. `frontend/node_modules` was already present and complete (no `npm install` needed).
- **Background processes on this machine were killed mid-task three times this session** (documented as a
  known issue). Nothing was lost each time because work was committed and pushed at small, frequent
  checkpoints rather than held as one large uncommitted change set — **this is now the working convention for
  this repo, not just a one-off mitigation**: commit (and push) after every meaningful edit, not only at
  "fully green" milestones. A `wip:` commit with a not-yet-passing test file is fine; the git history here
  isn't curated per-commit the way a reviewed PR would be.
- **Foreground tool calls cap out at 10 minutes (600000ms)** — a command that legitimately runs longer (the
  full backend suite: ~20-25 min this session, up from ~5 min pre-C6, likely just machine load; the full e2e
  suite: ~8-9 min) gets auto-promoted to a background task by the tool itself once it exceeds that cap. This
  is fine and expected — the fix is to **immediately chain a second foreground call in the same turn** that
  blocks on the background job's completion (e.g. poll a completion-marker line appended to the log file, or
  poll the OS process by PID, in a `while` loop with `sleep`, itself issued as one foreground call up to the
  same 10-minute cap — repeat if it doesn't finish in time). **A subagent does not get "woken back up" or
  notified on its own when a background command it started finishes** — that notification mechanism is for
  whatever spawned the subagent, not the subagent itself. Ending a turn with a background command still
  running that you need the result of just leaves you stalled; the top-level session has to notice and
  manually prompt again. Never do this — always block synchronously within the same turn until you have the
  real result, chaining multiple bounded polling calls back-to-back if one isn't enough.
- A separate AI agent runs a Django server for an **unrelated** project on port 8000 on occasion — not
  specifically checked this session, but nothing in this session's own work touched port 8000.
