# Session state — 2026-08-25 (session 5)

Written as a resume point. **Everything described as done is committed and pushed** —
`origin/master` is current. Working tree clean.

## Where the work is

Last code change: e2e specs + a real React bug fix, commit `b6fcd97`. Docs (RBAC-Roles.md,
Data-Dictionary.md, hcm/README.md, backlog) followed in `4506468`. This doc update is the final commit
of the session, pushed immediately after — run `git log -1` for the exact hash.

## Shipped today: C6 — interview scheduling, panel scorecards, background checks, external careers portal

The product owner said "let's finish C6" earlier this cycle and, when asked to scope this specific item down,
explicitly chose **"everything in one pass"** — build interview scheduling, panel scorecards,
background/reference-check tracking, AND the external careers portal together, not split across sessions.
Fourth C6 sub-item shipped (after mandatory-training compliance, succession/talent pools, and now this).
Spec: `docs/superpowers/specs/2026-08-25-recruitment-interviews-careers-portal-design.md`.

**Structural decision:** all four sub-parts landed in the existing `recruitment` app, not a new one — the
opposite call from succession's own precedent, and deliberately so: these are direct extensions of
`Applicant`/`Requisition` (the models `recruitment` already owns), read/written by the same audience
(`IsRecruiterOrHRAdmin`) plus a narrow row-level carve-out, and the careers portal doesn't even introduce a new
domain object, just a new (public) entry point into the same `Applicant`/`ConsentRecord` machinery. New files:
`recruitment/careers.py` (the entire public AllowAny surface in one file, deliberately, for auditability of the
system's first anonymous-write endpoint) and `recruitment/validation.py` (resume content-sniffing).

### A. Interview scheduling — `InterviewSession`

Ties an `Applicant` (validated at the `interview` stage) to one or more scheduled sessions: round number
(cheap multi-round support — just more rows), date/time, duration, free-text location/video-link, status, and
a plain M2M `interviewers` panel (no through-model needed). Read/write: recruiter/hr_admin, full access. An
assigned interviewer gets **read-only access to their own sessions only** — a row-level grant via
`IsRecruiterOrHRAdminOrAssignedInterviewer` and `get_queryset` filtering, not a role (any employee can be
tapped as a panelist). A `?mine=true` query param forces this row-scoping even for a recruiter/hr_admin who is
also occasionally a panelist — role alone can't distinguish "give me the admin view of every session"
(`ApplicantDetailPage.tsx`) from "give me only my own assignments" (`MyInterviewsPage.tsx`, new route
`/my-interviews`, `roles: []`).

**What an interviewer sees of the applicant:** a deliberately narrow, uniform-for-every-caller
`InterviewApplicantSummarySerializer` — name, requisition, current stage, CV/resume link. No demographics, no
email/phone/date_of_birth, no prior stage-event notes (considered and left out — recruiter-audience commentary
isn't vetted for an ad-hoc interviewer audience, and could itself anchor an interviewer's impression, same
concern as the scorecard blind-review below from a different angle).

### B. Panel scorecards — `InterviewScorecard`, blind review

Fixed three-criterion vocabulary (skill/communication/culture fit, 1-5 scale matching `performance`'s own
rating vocabulary — not a per-requisition configurable-criteria system, judged unnecessary complexity for
optional benefit) plus free-text comments and a recommendation (strong_hire/hire/no_hire/strong_no_hire).

**The access-control decision the brief flagged as needing real thought: blind review.** A scorecard's
rating/comments/recommendation are hidden from any OTHER interviewer on the same session until the viewer has
submitted their own — enforced in `InterviewScorecardSerializer.to_representation` (a small extra existence
query per row, negligible at this scale), not the permission class, which only decides row reachability.
Recruiter/hr_admin always see full detail immediately — they're aggregating for a decision, not forming an
independent first impression, which is the whole point blind review protects. No proxy-entry: only the named
interviewer may author/edit their own scorecard, not even hr_admin on their behalf (`interviewer` is
force-set server-side, never client-supplied). No edit-lock after submission — the blind-review gate already
prevents pre-submission anchoring, so a lock would only add friction for fixing a typo.

### C. Background / reference checks — `BackgroundCheck`, tracking only

Per `docs/MVP-Backlog.md` A3 #9 ("SA vetting is often manual/legal rather than API-shaped — low leverage"), no
vendor integration — a record per applicant of check type (reference/criminal_record/
qualification_verification/credit_check/other), status (not_started/requested/in_progress/cleared/flagged, no
`ALLOWED_TRANSITIONS` state machine since a real vetting process can legitimately move non-monotonically),
who requested it, when, and notes. Gated by the **existing** `IsRecruiterOrHRAdmin` unchanged — no per-field
tiering (the whole model is Sensitive by nature, matching the documented `performance.Review`/
`succession.SuccessionCandidate` "whole-endpoint, not per-field" exception already in `rbac_audit/tiers.py`).
**No interviewer access at all** — a real vetting outcome is exactly what an interviewer forming an independent
impression should not see, compounding the blind-review reasoning from a different angle.

### D. External careers portal — the highest-risk piece, built like a security review

`Requisition` gains `description` (general-purpose, not portal-exclusive) and `external_posting` (default
`False` — HR opts a requisition INTO public visibility; nothing becomes public automatically).
`Applicant` gains `source` (internal/portal — provenance only, never read by the stage machine, retention
handler, or hire flow) and `resume`/`resume_content_type`/`resume_size_bytes` (general, not portal-only — a
recruiter can attach a CV to an internally-sourced applicant too, via the same content-sniffing validation).

**Public endpoints** (`AllowAny`, in `recruitment/careers.py`): `GET /careers/postings/` (open +
`external_posting=True` requisitions only, narrow serializer) and `POST /careers/apply/`. A successful
submission creates a **real** `Applicant` row (`source=portal`) via `services.py::submit_portal_application` —
the SAME model, stage machine, retention/anonymisation-on-rejection path every internal applicant uses; no
staging/quarantine table (considered and rejected — it would mean every downstream consumer learning a second
applicant shape, exactly what the brief's "nothing downstream needs to know whether an applicant came from
HR-entered data or self-application" explicitly rules out). Containment against bad public input is at the
validation/throttling layer instead, not a second pipeline shape.

**Anti-abuse, concretely:**
- **Throttling** — three new scopes in `rbac_audit/throttling.py` mirroring `LOGIN_THROTTLES`'s exact shape
  (the system's second-ever anonymous-write surface): `careers_application_burst` (5/min/IP),
  `careers_application_sustained` (20/day/IP), `careers_application_email` (3/hour, keyed on the submitted
  email regardless of IP — closes the same distributed-attacker asymmetry `login_username` closes for login).
  Plus `careers_read` (60/min/IP) on the public postings list, defence-in-depth against scraping.
- **Upload validation** — `recruitment/validation.py` content-sniffs the resume (PDF/DOCX/JPEG/PNG magic
  bytes, 5MB cap) — duplicates `documents/validation.py`'s approach rather than importing it (`recruitment` may
  not import `documents`, a peer-app boundary; `documents/validation.py`'s own docstring already duplicates
  `policies/extraction.py` for the identical reason, so this is the same amount of debt the codebase already
  tolerates, not a new kind).
- **Honeypot** — a hidden, `aria-hidden` `website` field; a filled honeypot returns an ordinary 201 with no row
  created, indistinguishable from a real success to a bot.
- **Duplicate handling** — the existing `one_application_per_email_per_requisition` constraint is respected;
  `submit_portal_application` attempts the create and catches `IntegrityError` (not a racy pre-check), turning
  it into a clean `ValueError` → 400, never a 500.
- **CSRF** — none required, verified against `login_view`'s identical anonymous-POST shape: DRF's
  `SessionAuthentication.enforce_csrf` only runs once a request has actually authenticated via a session, which
  an anonymous careers-portal POST never does.
- **Consent gates storage, not submission** — an unconsented demographic value is silently dropped (stays
  `not_disclosed`), not a submission-blocking error; rejecting a genuine applicant's whole application over an
  unchecked box would be worse, and would incentivise ticking it just to get through.

**Frontend:** `CareersListPage`/`CareersPostingPage` (`/careers`, `/careers/:id`) are the SPA's **only** routes
outside `RequireAuth`/`AppShell` — App.tsx previously had every route behind one `RequireAuth` wrapper, so this
needed a genuinely new routing shape, not just a new `RequireRole` set. They reuse the existing `api` client
unchanged (its CSRF/credentials handling is harmless-but-inert for an anonymous caller, confirmed by inspection
and by the e2e run). `ApplicantDetailPage.tsx` gained Interviews (schedule form, panel picker, per-session
scorecard aggregate — recruiter/hr_admin territory, so no masking-aware UI needed there) and Background checks
sections. `RequisitionsPage.tsx` gained a description field and a "post to the public careers site" toggle.
`ApplicantsPage.tsx` gained a Source column.

### Real bugs the e2e run caught before they shipped (both fixed, not routed around)

1. `MyInterviewsPage`'s `ScorecardForm` read `existing` (an already-submitted scorecard) via `useState`'s lazy
   initializer — which only runs once, on mount. Since `existing` arrives asynchronously (the scorecards fetch
   resolves after the component's first render, `existing` starts `null`), the form silently kept showing its
   default 3/3/3 "new scorecard" values forever, never reflecting the interviewer's real, already-submitted
   ratings. Fixed with `key={mine?.id ?? 'new'}` on `<ScorecardForm>` to force a remount when the real data
   arrives — the standard React fix for "controlled form doesn't reflect an async-loaded prop."
2. A latent migration bug from C1, surfaced (not caused) by this session: `recruitment/migrations/
   0004_backfill_requisition_positions.py`'s `RunPython` step calls `services.py::backfill_requisition_positions`,
   which imports the LIVE `Requisition` model (not historical migration state) and runs an unrestricted
   queryset over it — meaning any field added to `Requisition` after migration 0004 was written breaks a
   from-scratch migration replay (`manage.py test` runs every migration from zero every time), because the
   live model's default SELECT references a column that doesn't exist yet at that point in schema history. This
   session's `description`/`external_posting` fields were simply the first to trigger it — nothing had added a
   `Requisition` field since 0004 shipped. Fixed by restricting that function's queryset to `.only("id")` (the
   loop never reads any other scalar field, only relations) — fixes it for this addition AND any future one.

## Backend / frontend status

**Backend: 1001 tests, OK** (up from 963 last session — net +38: ~55 new in `recruitment/test_api.py`,
18 new in `recruitment/test_careers.py`, plus a handful of small existing-file additions). `manage.py check`
and `makemigrations --check --dry-run` both clean. `tsc -b` and `oxlint` clean (same 2 pre-existing warnings
only: `AuthContext.tsx`, `ReferenceDataContext.tsx`).

**e2e: 59/66 passed** on the final full-suite run (`npm test`, ~10.5 min, `PYTHON` env var set per the
environment note below). Both new spec files — `recruitment-interviews.spec.ts` (3 tests: seeded-session
aggregate view, blind-review verified end-to-end across two real logins, non-panelist gets nothing) and
`careers-portal.spec.ts` (3 tests: anonymous listing scoping, duplicate-application clean error, and the full
portal-to-hire journey — anonymous apply → hr_admin advances to interview → schedules a session with a real
login → that interviewer scores it → hr_admin proposes an offer → recruiter approves/accepts (segregation of
duties) → hr_admin completes the hire) — **passed both standalone and as part of the full 66-test suite**, not
just in isolation.

The other 7 failures are the pre-existing/documented `settled()` timing-flake class, reconfirmed by reading
each failure's own error, not assumed:
- `contract-renewals.spec.ts` ×1, `core-hr.spec.ts` ×2 — one is the exact documented shape
  (`getByText('Loading…').toHaveCount(0)` timing out after 15s); the second (`line manager sees only their
  team`, `toBeGreaterThan(0)` receiving 0 rows) is in the same file, same large-employee-list territory, and is
  a very plausible cascade from the first test's failure in the same serial-execution file — recorded honestly
  as "same root-cause area, not byte-identical," not force-matched.
- `performance.spec.ts` ×4 — exactly the cascade SESSION-STATE already named: the "a full year" test times out
  (`Test timeout of 45000ms exceeded` waiting on mid-flow UI state), and the three tests that depend on that
  test's state (an agreement reaching `final_signed`, a `Flagged` improvement-plan row, an `Archived` period
  row) fail as a direct consequence, not independently.
- `compensation.spec.ts`/`ee-integrity.spec.ts` did **not** reproduce this run (both were flagged as
  intermittent last session) — consistent with the genuine per-run variance already documented, not evidence
  they're fixed.

Neither new spec's code, nor any spec this session didn't touch, shows a new failure mode.

## Next up — the menu (accurate as of today, not a recommendation)

- **C6 — remaining talent-depth sub-items** (mandatory-training compliance, succession/talent pools, and now
  interview scheduling/scorecards/background checks/careers portal are all shipped): performance
  calibration/moderation + 360° feedback is next in the roadmap's own listed order; also remaining: salary-
  review/bonus cycles + total-rewards statement; EE plan + consultation-forum records; real assessment-provider
  adapter — **this last one is blocked on a vendor decision (Sprint-0 action A4), not effort, same as it's been
  recorded every session — don't pick it expecting an effort-only slice.**
- **Leave / absence management** — still blocked on the cede-to-SAP decision (see below), not effort.
- **C3 — Identity & integrations**: OIDC/Entra SSO (ADR-004); SAP payroll read-only pull; leave read-only
  mirror (overlaps the blocked leave decision above); field-level step-up for `recruitment.Offer` pay fields.
- **C4 — Generic delegation & approvals**: generalise `SigningDelegation` → `Delegation(scope)`; "my
  approvals" inbox.
- **C5 — Labour relations**: disciplinary & grievance cases (warnings, hearings, outcomes, CCMA).
- **C7 — UX / NFR**: responsive + accessibility pass; server-side pagination/search (this would also be the
  real fix for the `/employees`-list-style performance flakes above); broader bulk import/export; report
  builder + scheduled emails.

`docs/sprints/backlog-uat1-and-c2-c7.md`'s C6 line now has mandatory-training compliance, succession/talent
pools, AND interview scheduling/scorecards/background checks/careers portal all ticked off — use that file, not
this narrative list, as the source of truth going forward.

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
  timeout.** Unchanged from last two sessions — same root-cause class, not chased (out of scope for this
  session's `recruitment`-app slice, same as it's been out of scope for two sessions running now).
- **`compensation.spec.ts`/`ee-integrity.spec.ts`** — flagged as newly-observed-and-intermittent last session;
  did not reproduce this session's two full runs. Neither spec's code has been touched in either of the last
  two sessions. Still worth a look if C7's server-side pagination is ever picked up.
- Parked residuals from C1 pt 2 (contract-renewal read/write role gaps, missing `@extend_schema`), the
  deliberate `let_lapse` gap, and the POPIA export's `documents`+`core_hr`+`rbac_audit`-only scope — all
  unchanged this session, see prior session-state history in git log for detail if needed.
- **From two sessions ago, unchanged:** historical free-text `TrainingRecord.title` rows never retroactively
  satisfy a `CourseRequirement` (no backfill attempted); no automatic enrollment when a `CourseRequirement`
  newly applies to someone.
- **From last session, unchanged:** no broader "role/career track" talent pool independent of a specific
  critical post (succession spec §2.2, §8); no manager-nominates/hr_admin-confirms two-step succession
  nomination workflow (succession spec §2.6, §8); unflagging a critical post does not cascade-withdraw its
  candidates (succession spec §2.3); no "sole ready successor is themselves at-risk elsewhere" data-quality
  enrichment (succession spec §2.9, §8); no reminders/notifications for succession.
- **New this session, recorded deliberately:** no configurable per-requisition interview scorecard criteria
  (fixed skill/communication/culture-fit only, spec §2.2, §8); no scorecard edit-lock after submission (blind
  review already prevents pre-submission anchoring, spec §2.2, §8); no proxy scorecard entry by hr_admin on an
  interviewer's behalf (spec §2.2, §8); an interviewer's applicant summary excludes prior stage-event notes
  (spec §3.1, §8); no calendar/video-conferencing integration — `InterviewSession.location` is free text (spec
  §2.1, §8); no staging/quarantine table for public careers-portal submissions before they enter the real
  pipeline — deliberate, containment is at validation/throttling instead (spec §2.5, §8); no applicant-facing
  "track your application status" self-service view on the careers portal (spec §8); no CAPTCHA on the public
  application form — throttling + content-sniffing + honeypot judged sufficient for this scale, a cheap future
  addition if abuse is actually observed in production (spec §8).

## Environment notes

- **GitHub Actions is billing-blocked** — every job fails in seconds. Push directly; local suites are the
  gate. Not a code problem.
- The venv at `C:\Users\KlopperW\AppData\Local\venvs\hcm` worked throughout this session with no rebuild
  needed. `frontend/node_modules` was already present and complete (no `npm install` needed).
- **The e2e suite's `backend-server.mjs` resolves Python via `$PYTHON`, then `backend/venv/Scripts/python.exe`,
  then bare `python` on PATH — none of which is this machine's actual venv location.** `npm test` fails
  outright (`ModuleNotFoundError: No module named 'django'`) unless you set `$PYTHON` explicitly:
  `PYTHON="C:\Users\KlopperW\AppData\Local\venvs\hcm\Scripts\python.exe" npm test` (or `npx playwright test
  <file>` for a single spec). Applied correctly from the very start of this session — no time lost to it this
  time, unlike two sessions ago.
- **This machine's `manage.py test` full-suite run took ~21 minutes this session** (1001 tests, up from an
  unrecorded-but-presumably-shorter time for 963 tests two sessions ago) and the full e2e suite took ~10.5
  minutes — noticeably slower under whatever load this machine was under today than prior sessions logged.
  Neither is a code regression (verified via the per-file/per-app runs along the way, all consistent with
  historical timing per-test); just record it so a future session doesn't panic and assume something broke
  when a full-suite run takes longer than a prior session's number suggested it "should."
- **Background processes get killed / tool calls time out on this machine.** Commands with an unpredictable
  runtime (full test suites, `npm test`) were started with `&` redirected to a log file, then polled with
  bounded `sleep`-loop `Bash` calls chained back-to-back in the foreground — never backgrounded and abandoned.
  Commit-and-push happened after every slice (spec → backend → backend tests → frontend pt1 → frontend pt2 →
  frontend pt3 → seed data → e2e specs → docs), matching the process lesson from prior sessions.
- A separate AI agent runs a Django server for an **unrelated** project on port 8000 on occasion — not
  specifically checked this session, but nothing in this session's own work touched port 8000, and the e2e
  backend (which does use 8000) ran cleanly throughout, both the two isolated new-spec runs and the final full
  suite.
