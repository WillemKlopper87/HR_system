# Session state — 2026-08-25 (session 2)

Written as a resume point. **Everything described as done is committed and pushed** —
`origin/master` is current.

## Where the work is

`HEAD = 3c9e841`, pushed. Working tree clean.

## Shipped today: C2 — employee documents & POPIA rights

Closes the fourth of the original five demoable-lifecycle breaks. Spec:
`docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md`.

| Item | Commits | State |
|---|---|---|
| Design spec | `9918b36` | Done, pushed |
| Backend — new `documents` app, `core_hr.Dependant`/`EmergencyContact` | `6ef959f` | Done, pushed |
| Frontend — `/my-documents`, EmployeeDetailPage sections, `/data-subject-requests` | `ff47988` | Done, pushed |
| Docs — RBAC-Roles.md, Data-Dictionary.md, hcm/README.md, MVP-Backlog.md, sprint doc | `cf9045b` | Done, pushed |
| e2e spec + two real bugs it caught and fixed | `3c9e841` | Done, pushed |

**What it is:** a new `documents` app (`EmployeeDocument`, `DataSubjectRequest`) plus two new `core_hr`
models (`Dependant`, `EmergencyContact`). `EmployeeDocument`'s sensitivity tier is a **row-level property**
driven by `document_type` (id_copy/employment_contract → Restricted, disability_verification/other →
Sensitive, qualification → Internal) rather than a `rbac_audit.tiers.FIELD_TIERS` entry — the generic
per-field shape doesn't fit a model whose sensitivity varies by row, not by field. Upload content is
server-sniffed (`documents/validation.py`), not filename-trusted, mirroring the fix `policies/extraction.py`
already established. Authenticated download reuses `policies.PolicyViewSet.download`'s exact `FileResponse`
pattern for both `EmployeeDocument.file` and the POPIA export artifact. Consent
(`rbac_audit.ConsentRecord`, new purpose `employee_documents`) is required only for `id_copy`/
`disability_verification` uploads. Writes to documents/dependants/emergency-contacts are **self-or-hr_admin
only** — deliberately narrower than the generic row-scope shape `learning.Certification` uses, since a
line_manager has no legitimate reason to manage a report's personal documents or third-party contacts.

`learning/views.py::wsp_atr_export` now unions `Certification` rows into the same CSV (a `record_type`
column) — qualifications weren't feeding WSP/ATR before this session; only `TrainingRecord` was. No new
`EmployeeDocument`↔`Certification` FK was added (would have required a peer-app coupling `documents` has no
need for); the two are related in meaning, not schema.

**The POPIA design decision (spec §6):** both export and erasure requests are submitted by the employee (or
by hr_admin on their behalf, since the exit cascade already disables a departed employee's login) and are
**reviewed and actioned by hr_admin, never auto-executed**. Erasure
(`documents/services.py::complete_erasure_request`) is a **hardcoded allow-list**, not a
`RetentionRule`-driven delete: it may only ever touch `EmployeeDocument` rows, `Dependant`/`EmergencyContact`
rows, and exactly three named `Employee` fields (`preferred_name`, `personal_email`, `phone` — the same set
RBAC-Roles.md already calls "ESS-editable"). It never touches `EmploymentEvent`, `EmploymentChange`,
`AuditLogEntry`, or `EmployeeVersion` history, regardless of any `RetentionRule` state — a hardcoded allow-list
rather than a rule lookup, specifically so a missing or misconfigured RETAIN rule can never accidentally let
an erasure request reach audit/employment-history data. This directly extends the employment-exit-states
spec's non-destructive philosophy (§6.3) into a second workflow that could otherwise have been tempted to
violate it.

**Full backend suite: 888 tests, OK** (up from 833) — verified with `manage.py test`, `manage.py check`, and
`makemigrations --check --dry-run`, all clean.

**e2e: 48/52 passed** on the full suite (`npm test`). All 7 new `documents.spec.ts` tests are green. The 4
failures are unrelated to this slice:
- `contract-renewals.spec.ts` and `core-hr.spec.ts` ×2 — the pre-existing, already-documented `settled()`
  timing flake on the large (153-employee) `/employees` list (see "Known defects" below) — reproduced with
  the identical error signature already on record.
- `performance.spec.ts` — one unrelated browser-session error ("Protocol error... session closed") in a
  module this slice never touched.

Two real bugs were caught and fixed by re-running `documents.spec.ts` in isolation after the first full-suite
run flagged 3 failures in it (the "always re-run after a fix" lesson from last session's onboarding work,
applied again here — see `hcm/frontend/e2e/documents.spec.ts`'s commit message for the full detail):
1. `DataSubjectRequestsPage` hides actioned (non-`submitted`) rows by default — the export/erasure tests
   were asserting against a row the moment it got filtered out of the DOM. Fixed by having the test check
   "Show actioned" before completing/declining.
2. One test searched the full `/employees` list (the known-slow page) purely to find one person's id. Fixed
   by resolving the id via a direct `page.request.get` API call instead, sidestepping the flaky page entirely
   rather than hoping it holds up.

## Next up (agreed sequence)

Sequencing is by **demoable lifecycle journey** — see `docs/MVP-Backlog.md` Part B. Four of the original five
lifecycle breaks are now closed: onboarding, org chart, personal documents (this session), offboarding. **One
remains, and it is genuinely the last item on this list:**

1. **Leave / absence management** — blocked on a decision, not effort (see below). Once resolved (either
   direction), there is nothing else queued on the demoable-lifecycle sequence. A future session should
   either pick this up after the decision lands, or ask the product owner what's next once it's confirmed
   there's nothing left to build without new direction — **do not guess at a next feature past this point.**

## Blocked on a decision, not effort

- **Leave / absence management.** Ceded to SAP as "mirror only" (C3), but nothing exists — not even the
  mirror — while the Policy Library ships a Leave Policy document with no system behind it. Needs the
  cede-to-SAP decision revisited before anyone builds it. This is now the **only** unresolved item on the
  demoable-lifecycle sequence (`docs/MVP-Backlog.md` Part B).

## Known defects (all pre-existing, none from today's work)

- **ESS phone edit does not persist across reload** (`ess-policies.spec.ts`). Real, reproduced at base
  commit, Sprint-15 territory.
- `core-hr.spec.ts` `settled()` timing flake on the large `/employees` list — reproduced again today, now
  also observed spilling into `contract-renewals.spec.ts` on the same page. Still unfixed; a real
  performance characteristic of `EmployeeListPage` (`fetchAllPages`'s unfiltered full-list + full-version
  fetch on first load) at the current ~153-employee seed scale, not a flake in the traditional
  non-deterministic sense — it is timing-dependent on machine load, which is why the exact failure count
  varies run to run (2 last session, 3-4 today). **If a future session has spare capacity, this is worth a
  real fix** (server-side default page size, or a lighter initial fetch) rather than continuing to route
  around it in new e2e specs, as this session's `documents.spec.ts` fix had to.
- Parked residuals from C1 pt 2: `ee_manager`/`recruiter`/`comp_manager` can read contract-renewal decisions
  spec §6 doesn't grant them; the two write actions serialise their response bypassing the tier gate; no
  `@extend_schema` on either action, so drf-spectacular infers the wrong body.
- **Known gap, decided deliberately (Data-Dictionary.md):** `let_lapse` still doesn't record a
  proposer/confirmer/reason on an `EmploymentChange` the way a genuine HR-initiated exit does.
- **New, recorded deliberately (this session):** `documents.EmployeeDocument`'s export in the POPIA workflow
  (`documents/services.py::generate_export`, called `_serialise_for_export`) is scoped to `documents` +
  `core_hr` + `rbac_audit` — it does not reach into `learning`/`performance`/`compensation`/`recruitment` for
  a fully exhaustive personal-data export. A genuinely complete POPIA export needs a `queries.py` seam per
  module that holds personal data. Spec §6.4/§9 records this as real, scoped-out follow-up work.
- **New, recorded deliberately:** `core_hr.Dependant`/`EmergencyContact`'s seeded `RetentionRule` rows
  (delete, 1 month) have no registered executor handler yet in `rbac_audit/retention.py` — same posture
  several pre-existing rules already carry (a rule with no handler is a no-op, never guessed at).

## Environment notes

- **GitHub Actions is billing-blocked** — every job fails in seconds. Push directly; local suites are the
  gate. Not a code problem.
- The venv at `C:\Users\KlopperW\AppData\Local\venvs\hcm` (built last session, outside OneDrive per
  `hcm/README.md`'s own recommendation) worked throughout this session with no rebuild needed.
  `frontend/node_modules` was already present and complete this session (no `npm install` needed).
- **The dev-only `hcm/backend/db.sqlite3` file was found badly stale this session** (migrations stuck at
  `core_hr.0006`, several apps' migrations never applied) and a plain `manage.py migrate` against it failed
  with a genuine migration-ordering issue (`establishment.0002_backfill_existing_employees` only declares a
  dependency on `core_hr.0006`, but its `RunPython` step imports the REAL current `EmployeeVersion` model —
  by design, per its own docstring — which needs `core_hr.0008`'s `contract_end_date` column to already
  exist; Django's migration executor doesn't guarantee that ordering from the declared dependency alone).
  This is gitignored, disposable, and **not used by `manage.py test`** (which builds its own fresh test DB
  through the full migration graph correctly) or by the e2e runner (which points at its own throwaway
  SQLite via `SQLITE_PATH`) — so it never blocked anything this session, but a future session running
  `manage.py runserver` locally for manual browser testing may hit this. If so: either add an explicit
  `("core_hr", "0008_employeeversion_contract_end_date_and_more")` dependency to
  `establishment/migrations/0002_backfill_existing_employees.py`, or just delete the stale `db.sqlite3` and
  re-run `migrate` + `seed_demo_data` fresh (it is gitignored and disposable either way).
- `e2e/backend-server.mjs` looks for `backend/venv` or `backend/.venv` by default; point it elsewhere with
  `PYTHON=/path/to/python.exe npm test` — needed again this session since the venv lives outside the repo.
- **Long-running commands (full backend suite ~5 min, full e2e suite ~7-13 min) were run synchronously in
  the foreground this session, redirected to a scratchpad log file rather than piped through `tail`**,
  exactly per last session's hard-won lesson — and it held up: no killed/stopped turns this session. A
  background task that the tool itself auto-promoted (exceeding the 2-minute default foreground timeout) was
  left running and picked back up via its completion notification rather than polled, which also worked
  cleanly. Two full e2e runs (~7 min and ~13 min) plus one full backend suite run (~5 min) is a lot of wall
  time in one session; a future session doing another full C-series slice should expect a similar time
  budget and plan accordingly rather than trying to shortcut verification.
- A separate AI agent runs a Django server for an **unrelated** project on port 8000 on occasion — checked
  free at the start of this session and stayed free throughout.
