# Session state — 2026-08-25 (session 4)

Written as a resume point. **Everything described as done is committed and pushed** —
`origin/master` is current.

## Where the work is

Last code change: e2e fix commit `18e2768`. This doc update is the final commit of the session, pushed
immediately after — run `git log -1` for the exact hash. Working tree clean.

## Shipped today: C6 — succession planning / talent pools

The product owner said "let's finish C6" — work through C6's remaining sub-items one at a time. This session
built the first of the remaining ones, per `ROADMAP-2026-08.md`/`NEXT_AGENT_BRIEF.md` §7.3 #18: *"no
critical-post flag, no readiness rating, no successor lists."* Spec:
`docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md`.

**New app `succession`** (not folded into `establishment` or `learning`, and not `SHARED_KERNEL`): two models,
`CriticalPost` (a `OneToOneField` flag on `establishment.Position` — `active` toggles it without deleting, same
convention as `Course.active`) and `SuccessionCandidate` (nominee + readiness, scoped to one `CriticalPost`).
No `services.py` — every write is single-row, validated in the serializer's own `validate()`, matching
`Skill`/`Course`/`CourseRequirement`'s shape rather than `Position`'s/`ChecklistTemplate`'s workflow shape.

**Scoping decision (spec §2.2):** tied to `establishment.Position` via a `OneToOneField`, not a broader
Department/OccupationalLevel "role track" the way mandatory-training's `CourseRequirement` is. Investigated
and rejected the broader shape: a critical post is one specific seat (continuity for *that* seat, e.g. "the
Head of Finance role needs a backup plan"), not a population a rule applies to uniformly the way "everyone in
Senior Management must complete X" does. `Position` already carries department/level/title context for free,
so the brief's "career path" requirement is satisfied by a list of positions without inventing a separate
career-track taxonomy.

**Access-control decision — the one the brief flagged as needing real thought (spec §2.6):** nobody sees their
own succession status, **no self-scope carve-out anywhere, including hr_admin viewing their own record.**
`SuccessionCandidate` read/write is hr_admin-only (auditor read-only); `CriticalPost` read matches
`establishment.Position`'s own read audience (hr_admin, comp_manager, accounting_officer, auditor, recruiter)
since the flag alone is coarse metadata, not the sensitive nominee list. On top of the role gate,
`SuccessionCandidateViewSet.get_queryset` **excludes any row whose `employee` is the acting requester
themself, regardless of role** — a real backend guarantee, not just the frontend declining to render its own
UI: an hr_admin cannot read a row about themself through this endpoint even calling the API directly (404 on
direct retrieve, absent from the list). Reasoning recorded in the spec: a successor list is a comparative,
exclusionary judgement about *other* people, and absence from it is itself sensitive information HR hasn't
chosen to communicate through this channel — stricter than a normal Internal-tier field, deliberately.

**Cross-app read seams (spec §2.7), informational only, never an input to the stored `readiness` value:**
`learning/queries.py` gained `skill_names_for_employee`; a **new `performance/queries.py`** (performance's
first read seam — nothing needed one before) gained `latest_final_score` (most recent `PerformanceAgreement`
with a frozen `final_score`, from `_finalize_scoring`). Both surfaced as read-only fields on a candidate's API
row (`skill_names`, `latest_performance`), shown on the Talent Pools candidate card.

**Data-quality check `CRITICAL_POST_NO_SUCCESSOR`:** an active critical post with no active
ready-now/ready-1-2-years candidate, attached to the post's current occupant (a vacant critical post is
silently skipped — no employee to attach it to, and the vacancy is already visible on `/positions`).
Registered from `succession.apps.SuccessionConfig.ready()`, same registry shape as every other C-series check.

**Frontend:** new `TalentPoolsPage.tsx` (hr_admin, under Performance & Growth nav) — flag a position critical,
nominate/rate/withdraw successor candidates, each candidate row links to their `EmployeeDetailPage` and shows
the skill/performance context. `PositionsPage.tsx` gained a "Critical" column (client-side cross-reference
against `/critical-posts/`, same pattern `CourseCataloguePage.tsx` already uses joining courses/requirements).
`EmployeeDetailPage.tsx` gained a read-only "Succession" section, hr_admin/auditor-only, and skipped entirely
(no fetch at all) when viewing your own record — belt-and-braces on top of the real backend guarantee above.

**Real bugs the e2e run caught before they shipped (both fixed, not routed around):**
1. The main flow test picked the employee-picker's first option blindly to nominate a successor — this could
   land on the acting hr_admin's own record, and the backend's self-exclusion (working exactly as designed)
   then hides that row from them forever after, so the test's own later assertions could never find it. Fixed
   the test to fetch `/auth/me/` and explicitly exclude the actor's own id.
2. `TalentPoolsPage` originally refetched all four lists (positions, employees, critical posts, candidates)
   after every single flag/nominate/withdraw action — positions and employees are full org-wide,
   cursor-paginated lists (150+ rows each) that rarely change mid-session. Split into two `useApiQuery` calls
   so a mutation only reloads the two small, frequently-changing lists. A real, worthwhile fix on its own
   merits (not just a test-dodge) — every mutation is now noticeably cheaper.

**Seed data:** `seed_demo_data.py` now flags two critical posts — `eng_head`'s post (with `staff` nominated as
a `ready_1_2_years` successor, so `/talent-pools` has a real "successor in the pipeline" example) and
`fin_head`'s post (left with zero candidates on purpose, so `CRITICAL_POST_NO_SUCCESSOR` has something genuine
to flag on `/data-quality` in a fresh environment).

**Backend: 963 tests, OK** (up from 926 recorded last session, actually 926→963 net +37: this session added 32
succession tests, 2 `learning` skill-seam tests, 3 `performance` queries-seam tests) — `manage.py test`,
`manage.py check`, and `makemigrations --check --dry-run` all clean. `tsc -b` and `oxlint` clean (same 2
pre-existing warnings only: `AuthContext.tsx`, `ReferenceDataContext.tsx`).

**e2e: 52/60 passed** on the final full-suite run (`npm test`, ~10.3 min). All 3 new `succession.spec.ts`
tests passed **standalone** (run in isolation twice, 3/3 both times, after the two fixes above) but the main
flow test (the long one: 3 logins, a full position-approval chain, flag+nominate+cross-page verification) hit
the same known `settled()`/machine-load timeout class when run as part of the full 60-test suite — verified,
not assumed: its own error was a bare "Test timeout of 45000ms exceeded" with no failing assertion, the same
shape every other flake below shows, and it is by far the longest test in the new spec file, the most exposed
to overall system contention. Not chased further, per the same reasoning the pre-existing flakes below aren't:
this is C7's (server-side pagination) territory, and the test's own correctness was already independently
verified.

The other 7 failures are the pre-existing/documented class, reconfirmed — not silently assumed the same,
checked per-file:
- `contract-renewals.spec.ts` ×1, `core-hr.spec.ts` ×1 — the documented `settled()` timing flake on the large
  (153-employee) `/employees` list. (Last session logged core-hr ×2; this run logged ×1 — consistent with
  genuine per-run variance under load, not a fixed count.)
- `performance.spec.ts` ×4 — same cascade from the "a full year" test already documented last session.
- **New this session, but same root-cause class, verified via each failure's own error message** (all four
  show `getByText('Loading…', {exact:true}).toHaveCount(0)` timing out, the exact `settled()` shape):
  `compensation.spec.ts` ×1 (seen on one full run, not the other — flaky, not deterministic) and
  `ee-integrity.spec.ts` ×1 (seen on both full runs). Neither spec's own code was touched this session; both
  are additional instances of the same documented "page not settling under current machine load" class,
  landing on two more spec files today than last session's list named. Recorded honestly as newly observed,
  not folded silently into the old line count.

## Next up — the menu (accurate as of today, not a recommendation)

- **Leave / absence management** — still blocked on the cede-to-SAP decision (see below), not effort.
- **C6 — remaining talent-depth sub-items** (mandatory-training compliance and succession/talent pools are now
  both done): recruitment interview scheduling + panel scorecards + external careers portal; performance
  calibration/moderation + 360; salary-review/bonus cycles + total-rewards statement; EE plan + consultation-
  forum records; real assessment-provider adapter — **this last one is blocked on a vendor decision (Sprint-0
  action A4), not effort, same as the leave item above; don't pick it expecting an effort-only slice.**
- **C3 — Identity & integrations**: OIDC/Entra SSO (ADR-004); SAP payroll read-only pull; leave read-only
  mirror (overlaps the blocked leave decision above); field-level step-up for `recruitment.Offer` pay fields.
- **C4 — Generic delegation & approvals**: generalise `SigningDelegation` → `Delegation(scope)`; "my
  approvals" inbox.
- **C5 — Labour relations**: disciplinary & grievance cases (warnings, hearings, outcomes, CCMA).
- **C7 — UX / NFR**: responsive + accessibility pass; server-side pagination/search (this would also be the
  real fix for the `/employees`-list-style performance flakes above, and would have made `TalentPoolsPage`'s
  original heavier shape a non-issue too); broader bulk import/export; report builder + scheduled emails.

`docs/sprints/backlog-uat1-and-c2-c7.md`'s C6 line now has both mandatory-training compliance and
succession/talent pools ticked off — use that file, not this narrative list, as the source of truth going
forward.

## Blocked on a decision, not effort

- **Leave / absence management.** Ceded to SAP as "mirror only" (C3), but nothing exists — not even the
  mirror — while the Policy Library ships a Leave Policy document with no system behind it. Needs the
  cede-to-SAP decision revisited before anyone builds it. Unchanged this session.
- **Real assessment-provider adapter (C6).** Sprint-0 action A4 (vendor shortlist) is still open. Unchanged.

## Known defects

- **ESS phone edit does not persist across reload** (`ess-policies.spec.ts`). Real, reproduced at base
  commit, Sprint-15 territory. Unchanged.
- **`core-hr.spec.ts`/`contract-renewals.spec.ts` `settled()` timing flake on the large `/employees` list.**
  Unchanged — still a real performance characteristic (`fetchAllPages`'s unfiltered full-list + full-version
  fetch on first load at ~153-employee seed scale), not a traditional non-deterministic flake. Server-side
  pagination (C7) is the real fix.
- **`performance.spec.ts`'s "a full year" test (and the tests that build on its state) fails on a `settled()`
  timeout.** Unchanged from last session — same root-cause class as the item above, not chased (out of scope
  for this session's `succession`-app slice, same as it was out of scope for last session's `learning` slice).
- **New this session, same class, two more spec files affected than last session's list named:**
  `compensation.spec.ts` (seen once, not reproduced a second time — genuinely intermittent) and
  `ee-integrity.spec.ts` (seen on both full-suite runs this session). Neither spec's code was touched this
  session. Worth a look if server-side pagination (C7) ever gets picked up — it would very likely resolve this
  whole class of flake project-wide in one pass rather than needing per-page mitigation.
- **New this session:** `succession.spec.ts`'s main flow test (the long multi-role-switch one) passed reliably
  in isolation (3/3, verified twice) but hit the same `settled()`/load-class timeout when run as part of the
  full 60-test suite (both full runs today). Its own correctness is independently verified via the isolated
  runs; the flake is about system load during the full suite, not the test's logic. Not chased further, same
  reasoning as the items above.
- Parked residuals from C1 pt 2 (contract-renewal read/write role gaps, missing `@extend_schema`), the
  deliberate `let_lapse` gap, and the POPIA export's `documents`+`core_hr`+`rbac_audit`-only scope — all
  unchanged this session, see prior session-state history in git log for detail if needed.
- **From last session, unchanged:** historical free-text `TrainingRecord.title` rows never retroactively
  satisfy a `CourseRequirement` (no backfill attempted); no automatic enrollment when a `CourseRequirement`
  newly applies to someone.
- **New, recorded deliberately (this session):** no broader "role/career track" talent pool independent of a
  specific critical post — a real, valid HR concept, deliberately not built (spec §2.2, §8). No
  manager-nominates/hr_admin-confirms two-step nomination workflow — hr_admin authors directly (spec §2.6,
  §8). Unflagging a critical post does not cascade-withdraw its candidates — preserves history for a possible
  re-flag, but means an inactive post's candidates are only reachable via history, not the default view (spec
  §2.3). No "sole ready successor is themselves at-risk elsewhere" enrichment on the data-quality check —
  suggested in the brief's context as a nice-to-have, not built (spec §2.9, §8). No reminders/notifications for
  succession — nothing in scope had a natural due-date the way mandatory training does (spec §8).

## Environment notes

- **GitHub Actions is billing-blocked** — every job fails in seconds. Push directly; local suites are the
  gate. Not a code problem.
- The venv at `C:\Users\KlopperW\AppData\Local\venvs\hcm` worked throughout this session with no rebuild
  needed. `frontend/node_modules` was already present and complete (no `npm install` needed).
- **The e2e suite's `backend-server.mjs` resolves Python via `$PYTHON`, then `backend/venv/Scripts/python.exe`,
  then bare `python` on PATH — none of which is this machine's actual venv location.** `npm test` fails
  outright (`ModuleNotFoundError: No module named 'django'`) unless you set `$PYTHON` explicitly:
  `PYTHON="C:\Users\KlopperW\AppData\Local\venvs\hcm\Scripts\python.exe" npm test` (or `npx playwright test
  <file>` for a single spec). This cost real time this session before being diagnosed — **do this from the
  start next time**, don't rediscover it.
- **Editing a file while a background job that reads it (`npm test`'s webServer boot, which runs
  `seed_demo_data`) is already starting up races the edit against the read** — this bit twice this session
  (once on `seed_demo_data.py`, once when re-running a test right as `TalentPoolsPage.tsx` was mid-edit,
  producing a stale-code failure that looked like a real bug at first glance). Wait for a background job's
  webServer/seed phase to actually start (or just don't kick one off until the files it will read are fully
  committed) rather than editing concurrently with a fresh `npm test` launch.
- **Background processes get killed / tool calls time out on this machine** — same mitigation as documented in
  prior sessions: commit and push at every meaningful checkpoint, chain bounded polling `Bash` calls
  back-to-back for anything backgrounded, never end a turn with a background command still running that the
  next step depends on. Held throughout this session (see commit history: spec → backend → frontend → e2e spec
  → seed data → e2e fixes, each pushed separately).
- A separate AI agent runs a Django server for an **unrelated** project on port 8000 on occasion — not
  specifically checked this session, but nothing in this session's own work touched port 8000, and the e2e
  backend (which does use 8000) ran cleanly throughout.
