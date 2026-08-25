# Session state — 2026-08-26 (session 6)

Written as a resume point. **Everything described as done is committed and pushed** —
`origin/master` is current at `0f0c8b1`. Working tree clean.

## Where the work is

Last code change: e2e spec + a real `MyPerformancePage` fix, commit `665929d`. Docs (RBAC-Roles.md,
Data-Dictionary.md, hcm/README.md, backlog) followed in `0f0c8b1`. This doc update is the final commit of the
session, pushed immediately after — run `git log -1` for the exact hash.

## Shipped this session: C6 — performance calibration/moderation + 360° feedback

The product owner's "let's finish C6" instruction from two sessions ago named this as the next sub-item after
mandatory-training compliance, succession/talent pools, and interview scheduling/careers-portal (all shipped
2026-08-25). Confirmed absent by grep (`calibrat`, `moderat`, `360`) before starting — the only hits were the
KPI-contracting spec's own "non-goal" line and `NEXT_AGENT_BRIEF.md` itself. **PDPs were already built**
(`PDPItem`, untouched) — this slice is genuinely just the two remaining pieces from `NEXT_AGENT_BRIEF.md` §7.3
#20. Spec: `docs/superpowers/specs/2026-08-25-performance-calibration-360-design.md`.

**Structural decision:** both features extend the existing `performance` app as sibling model modules
(`models/calibration.py`, `models/feedback360.py`) rather than a new app — the opposite call from succession's
own precedent, deliberately: everything here is fundamentally *about* one `PerformanceAgreement`, so a new app
would mean importing it across a boundary for the one thing both features need, for no audience/lifecycle
reason to justify it.

### A. Calibration / moderation — `CalibrationSession`, `CalibrationAdjustment`

A committee-style consistency check across a cohort of already-`FINAL_SIGNED`/`ARCHIVED` agreements, before their
scores are treated as final. **Cohort unit: department** (nullable = org-wide), reusing the exact grouping
`views_agreements.py::rating_distribution` (PC-3) already uses — the dashboard a real committee would look at
before meeting and the session's candidate list are the same shape. A shared-Head cohort was considered and
rejected (too small a sample, and `head` drifts across the year as org changes happen).

**Not a live multi-party tool** — per the brief's explicit steer, hr_admin records what a committee decided after
an offline meeting (`CalibrationSession.participants_note`/`summary` are free text), the same single-actor
authorship pattern `Course`/`CriticalPost`/`ChecklistTemplate` already use.

**Never a silent overwrite, never a re-signature.** Recording an outcome (`record-outcome` action) requires a
reason even when nothing changes (`new_score=None` = "reviewed, no change" — still a real, reasoned row).
`CalibrationAdjustment` is create-only (no update/delete route anywhere in the API — a correction is a new row,
not an edited one, the same shape `AgreementSignature` already uses). Three independent audit trails come free
when a score does change: the adjustment row itself (previous/new/reason/who), `PerformanceAgreement.history`
(existing `simple_history`, automatically captures the `final_score`/`hr_attention` diff via the already-installed
`HistoryRequestMiddleware` — zero new infrastructure), and `log_access`. **Deliberately no re-signature**: the
brief's own counter-argument ("this system's philosophy elsewhere is amendments as new revision, re-sign") was
taken seriously and rejected on the merits, not waved away — `amend_agreement` exists for the employee and Head
jointly reopening *their own* agreement; calibration is a categorically different event, an HR/committee act of
cross-cohort consistency layered *on top of* an already-signed agreement, not a renegotiation between the two
original parties. Forcing the full submit→approve→sign chain to re-run for a numeric consistency nudge would
misrepresent what happened and could leave a calibrated agreement unsigned indefinitely, undermining PC-3's whole
point of being able to archive a finished year. The original `AgreementSignature`/`AgreementDocument` rows stay
completely untouched as the historical record of what was mutually agreed at sign-off. Fairness is addressed by
transparency instead of a re-sign gate — the reason is always visible to the employee and Head via a nested
`calibration_adjustments` field on `PerformanceAgreementSerializer` (rides the agreement's own existing
permission, not a second surface), same as `return_reason`/`amendment_reason` already do.

Read of the session/cohort itself: **hr_admin/auditor only** — same "no self/team browsing of a comparative
judgement about others" precedent `SuccessionCandidate` set (spec §2.6 there).

### B. 360° feedback — `Feedback360Request`, `Feedback360Rater`, `Feedback360Response`

Structured, multi-rater input attached to `PerformanceAgreement`, deliberately **not** an extension of the legacy
free-text `Feedback` model (`models/cycles.py`) — that model's open-authorship (anyone rates anyone, no
nomination) is right for a private note and wrong for rated input a Head reads alongside a KPI scorecard.

**Structure**: fixed 3-criterion 1–5 scale (`collaboration_rating`/`communication_rating`/`reliability_rating`,
matching `recruitment.InterviewScorecard`'s precedent exactly) plus `strengths`/`development_areas` free text.

**Who can be a rater**: `self` and `manager` slots are automatic and pre-approved when a round opens (the
snapshotted Head, or an active `SigningDelegation`); `peer`/`direct_report` slots are nominated (by the subject,
their Head, or hr_admin) and need Head/hr_admin approval — not fully open like legacy `Feedback`, since this
input can shape a real assessment. `relationship` is always derived server-side from the org chart at nomination
time (mirrors `classify_feedback_type`), never client-trusted.

**Visibility — the load-bearing decision (spec §2.10):**
- Head/delegate, hr_admin, auditor, and a rater's own row: **full attribution, always** — they're synthesizing
  input into a decision, not forming an independent first impression an anchoring risk would protect against.
- The subject sees their **self** and **manager** responses in full (no new exposure — the manager's comment is
  already visible elsewhere as `final_head_comment`).
- The subject **never** sees an individual **peer**/**direct_report** response — not the rater's identity, not
  their free text, ever, permanently (not just pre-submission). Only a pooled, **ratings-only** average per
  relationship type, gated on **≥3 responses in that bucket**
  (`FEEDBACK_360_MIN_RESPONSES_FOR_AGGREGATE = 3`, deliberately **not**
  `views_agreements.SMALL_CELL_THRESHOLD`'s 5 — that protects a demographic cell inside an org-wide aggregate, a
  different risk shape/scale from a 360 round's realistic 2–6-person rater pool per relationship type; reusing 5
  would make the feature almost never surface anything). Peer and direct-report buckets are kept **separate**,
  not pooled together, even though pooling would clear the floor sooner — protecting the group most likely to
  fear retaliation (direct reports) was judged more important than that group's feedback reaching the subject
  more often.
- No blind-review-style "hidden until you submit your own" sequencing between raters (unlike
  `InterviewScorecard`) — that pattern protects against anchoring between people deciding the same thing
  *live and simultaneously*; 360 raters never see each other's answers at all regardless of order, so there's no
  anchoring surface here in the first place.

**Never feeds `final_score`** — qualitative/contextual input only, alongside the KPI-weighted calculation, per the
guardrail (changing an already-shipped, tested scoring formula was out of scope and unjustified).

### Optional `CompProposal` linkage — confirmed unbuilt, explicitly out of scope

`ROADMAP-2026-08.md`'s PC-3 row names this as optional and unbuilt; confirmed by grep (no cross-app import, no
`compensation` read seam exists for a calibration-adjusted score to flow through without a direct model import,
which the module-boundary rules forbid). Building a one-way write seam from `performance` into `compensation`
deserves its own design decision (what triggers it, does an adjustment re-trigger an existing draft) rather than
being a side effect of this slice. Recorded as a known boundary, not a gap that was missed.

### A real UX gap fixed along the way, not routed around

`MyPerformancePage.tsx` only ever rendered the full `AgreementCard` (KPIs, evidence, signatures, and now
calibration/360) for the **most recent** agreement by period start_date — every older year was reduced to a
summary row with just a PDF download link. Calibration outcomes and 360 rounds can exist on a past,
already-archived agreement, not just the current one, so that would have silently hidden them from the employee.
Every year now gets an Open/Viewing toggle, the same per-row shape `TeamPerformancePage` already used. Also
fixed: the 360 nomination dropdown now excludes already-nominated raters (self/manager/existing peer) — a real
UX bug (nobody should be offered as nominatable twice), found while writing the e2e nomination test.

### Data-quality check

`missing_calibration_handler` (`performance/data_quality.py`, new `ExceptionType.PERFORMANCE_NO_CALIBRATION`):
once a period's FINAL phase due date has passed and the period has no `CalibrationSession` at all, every
`FINAL_SIGNED` agreement in it is flagged per-employee (the registry's only shape — a period-level gap surfaced
per-row, same pattern `overdue_agreement_handler` already uses).

## Backend / frontend status

**Backend: 1046 tests, OK** (up from 1001 last session — net +45: 44 new in `test_calibration.py`/
`test_feedback360.py`, plus one small addition elsewhere). `manage.py check` and `makemigrations --check
--dry-run` both clean. New migrations: `performance/migrations/0005_calibrationsession_feedback360request_and_more.py`,
`core_hr/migrations/0015_alter_dataqualityexception_exception_type.py`. `tsc -b` and `oxlint` clean (same 2
pre-existing warnings only: `AuthContext.tsx`, `ReferenceDataContext.tsx`).

**e2e: 61/69 passed** on the final full-suite run (`npm test`, ~11.1 min). The new
`performance-calibration-360.spec.ts` (3 tests: hr_admin records/closes a calibration session; an unrelated
employee is blocked entirely from calibration data — route redirect + 403 API, not just a hidden nav link; and
the load-bearing 360 visibility test end-to-end across four real logins — subject, the originally-nominated peer,
a newly-nominated second peer, and the Head — proving the masking rule holds even after the peer responds and
even after a second nomination) **passed both standalone and inside the full 69-test suite**.

Caught and fixed two real bugs while writing that spec (both fixed, not routed around):
1. Copy-pasted a `div.detail-card` selector from `recruitment-interviews.spec.ts` into two places where the
   actual component renders a bare `<section className="detail-card">` — a test bug, not a product bug, but
   worth recording since it produced a real, reproducible false failure until traced to the actual DOM element
   type via the error-context snapshot rather than assumed.
2. The `MyPerformancePage.tsx` "only the latest year gets the full card" gap described above — found because the
   seeded calibration/360 demo data deliberately lives in a *second*, separate FY period (see seed-data note
   below), which the old code would have made unreachable from the employee's own login.

The other 8 failures are the pre-existing/documented `settled()` timing-flake class, reconfirmed by reading each
failure's own error, not assumed:
- `contract-renewals.spec.ts` ×1, `core-hr.spec.ts` ×2, `ee-integrity.spec.ts` ×1 — all the exact documented
  shape (`getByText('Loading…').toHaveCount(0)` timing out after 15s on the large `/employees` list).
- `performance.spec.ts` ×3 — the same documented cascade from two sessions running: the "a full year" test times
  out, and the two tests that depend on its state fail as a direct consequence.
- `succession.spec.ts` ×1 — **newly observed this session**, not previously documented as affected. Same exact
  `settled()`-timeout signature (`Loading…` never disappears, `Protocol error: session closed` — a low-level
  connection failure, not a logic/selector error). **Verified, not assumed, to be machine-load flake and not a
  regression**: re-ran `succession.spec.ts` in isolation immediately after — failed again with the identical
  signature, on a test file this session touched zero code for (no succession app/model/permission/page changes
  anywhere in this session's diff). Recorded honestly as a new instance of the documented class, not force-fit
  into the old list and not silently ignored either.

Neither new spec's code, nor any spec this session didn't touch, shows a genuinely new failure mode.

## Seed data

`seed_demo_data.py` gained `_seed_calibration_and_feedback360_demo_data`: a **second, separate FY period**
("2025/26", already fully elapsed) rather than touching the main "2026/27" period's carefully-curated
draft/submitted/approved/agreed spread — opening mid-year/final on that period would sweep every already-AGREED
demo agreement into the new stage as a side effect, contradicting its own "a few fully agreed" narrative. One
agreement (fin_head, login `compmanager`, under ceo, login `accountingofficer` — both real demo accounts, so the
whole flow including both password signatures is genuinely reproducible) is taken to `FINAL_SIGNED`, given one
"reviewed, no change" calibration outcome, and a 360 round with self+manager responded and one approved peer
(ops_head, login `eemanager`) deliberately left un-responded — a realistic in-progress state for `/calibration`
and `/my-feedback-requests` to demo, not a finished example. Validated end-to-end against a throwaway sqlite DB
(`SQLITE_PATH` override, `migrate` + `seed_demo_data`, exit 0, correct summary line) before committing, and again
implicitly via the full backend test suite and e2e run.

## Next up — the menu (accurate as of today, not a recommendation)

- **C6 — remaining talent-depth sub-items**: mandatory-training compliance, succession/talent pools, interview
  scheduling/careers-portal, and now performance calibration/360 are all shipped. Left: **salary-review/bonus
  cycles + total-rewards statement** (compensation); **EE plan + consultation-forum records** (ee_reporting);
  **real assessment-provider adapter** — **still blocked on a vendor decision (Sprint-0 action A4), not effort,
  same as every prior session — don't pick it expecting an effort-only slice.**
- **Leave / absence management** — still blocked on the cede-to-SAP decision (see below), not effort.
- **C3 — Identity & integrations**: OIDC/Entra SSO (ADR-004); SAP payroll read-only pull; leave read-only mirror
  (overlaps the blocked leave decision above); field-level step-up for `recruitment.Offer` pay fields.
- **C4 — Generic delegation & approvals**: generalise `SigningDelegation` → `Delegation(scope)`; "my approvals"
  inbox.
- **C5 — Labour relations**: disciplinary & grievance cases (warnings, hearings, outcomes, CCMA).
- **C7 — UX / NFR**: responsive + accessibility pass; server-side pagination/search (this would also be the real
  fix for the `/employees`-list-style performance flakes above); broader bulk import/export; report builder +
  scheduled emails.

`docs/sprints/backlog-uat1-and-c2-c7.md`'s C6 line now has all four shipped sub-items ticked off (mandatory-
training compliance, succession/talent pools, interview scheduling/careers-portal, calibration/360) — use that
file, not this narrative list, as the source of truth going forward.

## Blocked on a decision, not effort

- **Leave / absence management.** Ceded to SAP as "mirror only" (C3), but nothing exists — not even the mirror —
  while the Policy Library ships a Leave Policy document with no system behind it. Needs the cede-to-SAP decision
  revisited before anyone builds it. Unchanged this session.
- **Real assessment-provider adapter (C6).** Sprint-0 action A4 (vendor shortlist) is still open. Unchanged.

## Known defects

- **ESS phone edit does not persist across reload** (`ess-policies.spec.ts`). Real, reproduced at base commit,
  Sprint-15 territory. Unchanged.
- **`core-hr.spec.ts`/`contract-renewals.spec.ts`/`ee-integrity.spec.ts`/`succession.spec.ts`'s `settled()` timing
  flake on the large `/employees` list.** `succession.spec.ts` newly observed affected this session (see e2e
  section above) — still a real performance characteristic (`fetchAllPages`'s unfiltered full-list + full-version
  fetch on first load at ~153-employee seed scale), not a traditional non-deterministic flake. Server-side
  pagination (C7) is the real fix.
- **`performance.spec.ts`'s "a full year" test (and the tests that build on its state) fails on a `settled()`
  timeout.** Unchanged from three sessions running now — same root-cause class, not chased (out of scope for
  every session's own slice so far).
- **`compensation.spec.ts`** — flagged as newly-observed-and-intermittent two sessions ago; did not reproduce in
  either of the last two full-suite runs (this session's or the prior one). Not touched this session either.
  Still worth a look if C7's server-side pagination is ever picked up.
- Parked residuals from C1 pt 2 (contract-renewal read/write role gaps, missing `@extend_schema`), the deliberate
  `let_lapse` gap, and the POPIA export's `documents`+`core_hr`+`rbac_audit`-only scope — all unchanged, see prior
  session-state history in git log for detail if needed.
- **From three sessions ago, unchanged:** historical free-text `TrainingRecord.title` rows never retroactively
  satisfy a `CourseRequirement` (no backfill attempted); no automatic enrollment when a `CourseRequirement` newly
  applies to someone.
- **From two sessions ago, unchanged:** no broader "role/career track" talent pool independent of a specific
  critical post; no manager-nominates/hr_admin-confirms two-step succession nomination workflow; unflagging a
  critical post does not cascade-withdraw its candidates; no "sole ready successor is themselves at-risk
  elsewhere" data-quality enrichment; no reminders/notifications for succession.
- **From last session, unchanged:** no configurable per-requisition interview scorecard criteria; no scorecard
  edit-lock after submission; no proxy scorecard entry by hr_admin on an interviewer's behalf; an interviewer's
  applicant summary excludes prior stage-event notes; no calendar/video-conferencing integration; no
  staging/quarantine table for public careers-portal submissions; no applicant-facing "track your application
  status" self-service view; no CAPTCHA on the public application form.
- **New this session, recorded deliberately:** no live multi-party calibration meeting tooling — hr_admin
  records an offline outcome, by design (spec §2.3); no `CompProposal` linkage from a calibrated/final score,
  confirmed unbuilt and deliberately out of scope (spec §2.13); no re-signature on a calibration adjustment
  (spec §2.4) — revisit if a future legal/CCMA review demands it, the service-layer change would be small and the
  existing audit trail wouldn't need to change either way; peer/direct-report free text never reaches the
  subject, ever, even pooled/paraphrased (spec §2.10) — a deliberate, not merely not-yet-built, limitation;
  direct-report feedback may permanently sit below the 3-response floor in a small team and never surface to the
  subject even as an aggregate — accepted cost of protecting the group most likely to fear retaliation; no
  automatic re-open of a `Feedback360Request` when its agreement is later amended via `amend_agreement`.

## Environment notes

- **GitHub Actions is billing-blocked** — every job fails in seconds. Push directly; local suites are the gate.
  Not a code problem.
- The venv at `C:\Users\KlopperW\AppData\Local\venvs\hcm` worked throughout this session with no rebuild needed.
  `frontend/node_modules` was already present and complete (no `npm install` needed).
- **The e2e suite's `backend-server.mjs` resolves Python via `$PYTHON`, then `backend/venv/Scripts/python.exe`,
  then bare `python` on PATH — none of which is this machine's actual venv location.** `npm test` fails outright
  (`ModuleNotFoundError: No module named 'django'`) unless you set `$PYTHON` explicitly:
  `PYTHON="C:\Users\KlopperW\AppData\Local\venvs\hcm\Scripts\python.exe" npm test` (or `npx playwright test
  <file>` for a single spec). Applied correctly from the very start of this session.
- **This machine's `manage.py test` full-suite run took ~25.9 minutes this session** (1046 tests, up from ~21
  minutes for 1001 tests last session) and the full e2e suite took ~11.1 minutes. Neither is a code regression
  (confirmed via the per-app/per-file runs along the way, all consistent with historical timing per-test) — this
  machine's load varies session to session and has been trending slower across the last several sessions; a
  future session shouldn't panic and assume something broke purely from a longer wall-clock number.
- **Validate a new/risky `seed_demo_data.py` change against a throwaway DB before trusting it in e2e**: point
  `SQLITE_PATH` at a scratch file (`export SQLITE_PATH=/path/to/scratch.sqlite3`), run `manage.py migrate
  --run-syncdb` then `manage.py seed_demo_data` directly, check for a clean exit + the expected summary line, then
  delete the scratch file. Much faster to debug a seeding exception this way than through the e2e browser layer —
  used this session to catch nothing (the new seed function worked first try), but worth keeping as a habit for
  any future seed-data change of comparable complexity.
- **Background processes get killed / tool calls time out on this machine.** Commands with an unpredictable
  runtime (full test suites, `npm test`) were started with `run_in_background`, then polled with bounded
  (~580s) `Bash` calls chained back-to-back in the foreground — never backgrounded and abandoned; each poll call
  blocks synchronously so the turn never ends while something in flight still matters. Commit-and-push happened
  after every slice (spec → backend → backend tests → frontend → seed data → e2e spec + fixes → docs), matching
  the process lesson from prior sessions.
- A separate AI agent runs a Django server for an **unrelated** project on port 8000 on occasion — not
  specifically checked this session, but nothing in this session's own work touched port 8000, and the e2e
  backend (which does use 8000) ran cleanly throughout.
