# Session state — 2026-08-25

Written as a resume point. **Everything described as done is committed and pushed** —
`origin/master` is current.

## Where the work is

`HEAD = 351d11f`, pushed. Working tree clean.

## Shipped today: C1 part 3 slice 3 — onboarding/offboarding checklists

C1 part 3 is now **fully done, all three slices** (exit states + access cascade shipped
2026-08-20/21; this session closed the third and final piece). Spec:
`docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md`.

| Item | Commits | State |
|---|---|---|
| Design spec | `7565b12` | Done, pushed |
| Backend — new `onboarding` app, `core_hr/lifecycle_hooks.py` registry | `e397ab1` | Done, pushed |
| Frontend — `/checklist-templates`, `/checklists`, seed demo data | `5044774` | Done, pushed |
| Docs — RBAC-Roles.md, Data-Dictionary.md, hcm/README.md, sprint doc, MVP-Backlog.md | `9c8f69e` | Done, pushed |
| e2e spec + two real bugs it caught and fixed | `351d11f` | Done, pushed |

**What it is:** versioned `ChecklistTemplate`/`ChecklistTemplateItem` (a flat ordered task
list per direction — onboarding or offboarding — deliberately simpler than
`performance.AgreementTemplate`, no sections/signing/scoring) and
`ChecklistInstance`/`ChecklistInstanceItem` (snapshotted from the template at creation, so a
later template edit never rewrites a live checklist). Instances are created automatically:
onboarding on `EmployeeManager.hire()`, offboarding when an ending-type `EmploymentChange`
executes — including a lapsed fixed-term contract, which routes through the same execute
path. Both triggers go through a new `core_hr/lifecycle_hooks.py` registry (same shape as
`access_cascade.py`/`data_quality.py`) since `core_hr` is SHARED_KERNEL and can't import the
new domain app. Task completion is gated by `owner_role` + reporting chain: `hr_admin`
completes anything; a `line_manager` only a `line_manager`-owned task for their own reports;
nobody self-completes their own checklist (several tasks are attestations *about* the
employee, not *by* them).

**Full backend suite: 833 tests, OK** (up from 774 at the last recorded run) — verified with
`manage.py test`, `manage.py check`, and `makemigrations --check --dry-run`, all clean.

**e2e: 42/45 passed** on the full suite (`npm test`), including all 5 of the new
`onboarding.spec.ts` tests. The e2e run itself caught two real bugs before this got called
done, both fixed and re-verified:
1. `ChecklistTemplatesPage` called the paginated list endpoint with plain `api.get` instead
   of `fetchAllPages`, throwing `templates.map is not a function` — this single unhandled
   render error cascaded into ~10 unrelated timeouts across other spec files on the first
   full run (an important lesson: **always re-run the full suite after an e2e fix**, not
   just the one spec file, since one broken page can degrade everything after it).
2. The new spec's own locators were too broad — `manager` (eng_head) manages dozens of
   seeded employees, not just the one with pre-completed demo tasks, so a bare task-label
   text search matched many rows; the offboarding test had the same issue once
   `contract-renewals.spec.ts`'s `let_lapse` action (which creates a *second* real
   offboarding checklist via the same execute path) ran earlier in the same suite. Both
   fixed by scoping to the specific employee's `.detail-card`.

The 3 remaining e2e failures on the first full run (`core-hr.spec.ts` ×2) are the
**pre-existing, already-documented `settled()` timing flake** — reproduced with the
identical error signature this session recorded before ("Loading…" still visible after
15s on the large employee list). Unrelated to this slice; not touched.

No port-config workaround was needed this session — 8000/5173 were free throughout, so
`playwright.config.ts`/`vite.config.ts`/`e2e/backend-server.mjs` were never touched.

## Next up (agreed sequence)

Sequencing is by **demoable lifecycle journey**, not technical dependency — see
`docs/MVP-Backlog.md` Part B.

1. **C2 — employee documents.** Closes the third of the original five lifecycle breaks
   (onboarding, org chart and offboarding are now all done). The consent/tiering plumbing
   already exists, so this is mostly a new model plus the policies module's existing
   authenticated-download pattern.
2. **Leave / absence management** — blocked on a decision, not effort (see below). Highest
   remaining demo value on the backlog.

## Blocked on a decision, not effort

- **Leave / absence management.** Ceded to SAP as "mirror only", but nothing exists — not
  even the mirror — while the Policy Library ships a Leave Policy document with no system
  behind it. Needs the cede-to-SAP decision revisited before anyone builds it.

## Known defects (all pre-existing, none from today's work)

- **ESS phone edit does not persist across reload** (`ess-policies.spec.ts`). Real,
  reproduced at base commit, Sprint-15 territory.
- `core-hr.spec.ts` `settled()` timing flake — reproduced again today, still unfixed.
- Parked residuals from C1 pt 2: `ee_manager`/`recruiter`/`comp_manager` can read
  contract-renewal decisions spec §6 doesn't grant them; the two write actions serialise
  their response bypassing the tier gate; no `@extend_schema` on either action, so
  drf-spectacular infers the wrong body.
- **Known gap, decided deliberately (Data-Dictionary.md):** `let_lapse` still doesn't record
  a proposer/confirmer/reason on an `EmploymentChange` the way a genuine HR-initiated exit
  does — it fast-paths through `record_executed_exit`. The access cascade AND (as of today)
  the offboarding checklist both still fire correctly either way, since both hang off
  `execute_employment_change` itself, not off how the change arrived there.

## Environment notes

- **GitHub Actions is billing-blocked** — every job fails in seconds. Push directly; local
  suites are the gate. Not a code problem.
- **No project venv exists in this repo** — `hcm/backend/venv`/`.venv` isn't checked in and
  wasn't present at the start of this session. This session built one at
  `C:\Users\KlopperW\AppData\Local\venvs\hcm` (per `hcm/README.md`'s own recommendation to
  keep it outside OneDrive) and `frontend/node_modules` needed `npm install` (only ~29
  packages were present, an incomplete/stale install). A next session may need to re-check
  both exist before running anything.
- `e2e/backend-server.mjs` looks for `backend/venv` or `backend/.venv` by default; point it
  elsewhere with `PYTHON=/path/to/python.exe npm test`.
- Background agents/processes have been killed mid-task before on this machine. Commit
  checkpoints early rather than holding a large uncommitted change set — this session
  committed after each of spec/backend/frontend/docs/e2e rather than one giant commit.
- **Long-running commands (full backend suite, full e2e suite) buffer their output when
  piped through `tail`** — nothing streams until the process exits, which can look
  indistinguishable from "hung." Redirect to a file (`... > log 2>&1`) instead of piping
  through `tail` if you need to inspect progress before completion; either way, run these
  synchronously in the foreground and wait for the actual tool result rather than
  backgrounding + polling — a background task's completion notification does not reliably
  resume a killed/stopped turn.
- A separate AI agent runs a Django server for an **unrelated** project on port 8000 on
  occasion — check before assuming it's free (it was free throughout this session).
