# HR_system (Sentech HCM) — Next Agent Brief

**Written:** 2026-08-18 · **Against:** `master` @ `0d6ea3a` (== `origin/master`, working tree clean)
**Repo:** https://github.com/WillemKlopper87/HR_system · **App code:** `hcm/` (Django 5.2 + DRF backend, React 19 + TS frontend)

This is a *review-and-handoff* document: what exists, what was verified today, what the previous agent would do differently
with hindsight, and what's left. The sprint-by-sprint source of truth remains `Sprint-Plan-HCM-System.md`; this file is
the 15-minute onboarding on top of it.

---

## 1. Verified state (2026-08-18, run locally — not taken from docs)

| Check | Result |
|---|---|
| `git status` / `git log` | clean; 14 commits; HEAD `0d6ea3a` pushed |
| GitHub Actions `hcm-ci.yml` | **green on every one of the last 8 pushes** (last run 2026-08-14) |
| `manage.py check --fail-level WARNING` | OK (Python 3.13 venv at `hcm/backend/venv`) |
| `manage.py makemigrations --check --dry-run` | no changes |
| `manage.py test` | **403 / 403 pass** (SQLite) |
| `npm run lint` (oxlint) | 2 warnings only (react fast-refresh, `AuthContext.tsx:44`, `ReferenceDataContext.tsx:73`) |
| `npm run build` (`tsc -b && vite build`) | OK — main chunk 385 kB, `MyIdentityVerificationPage` chunk 1.3 MB (face-api, lazy-loaded by design) |
| Size | backend ≈14 k lines Python incl. ≈5 k tests, 10 apps, 20 migrations; frontend ≈8.1 k lines TS/TSX in 44 files, 6.9 kB CSS total |

Everything the sprint plan marks **done** is genuinely done, tested and pushed. This project is in noticeably better shape
than the sibling projects (CI has never been red; docs were kept in sync every sprint).

## 2. What has been built

Sprint plan backlog, in order (all `Status: done` blocks in `Sprint-Plan-HCM-System.md` carry implementation notes,
design-tension callouts, acceptance verification and test counts — read the block for the sprint you're touching):

| Sprint | Module / app | Commit |
|---|---|---|
| 0–2 | Planning docs, `core_hr` (employees, org, lifecycle, effective-dated history), `rbac_audit` (roles, row-scope, field tiers, consent, audit log) | `53c7d09` |
| 3 | Core HR dashboards & admin UI, session auth for the SPA | `445b39f` |
| 4–5 | `recruitment` — requisitions → applicants → offers → hire automation | `787fcd3` |
| 6–7 | `performance` — goals, review cycles, self/manager reviews, feedback | `3af2411` |
| 8–9 | `learning` — skills, certs, training, WSP/ATR CSV export | `68bef58` |
| 10–11 | `compensation` — pay bands, comp-proposal workflow, benefits | `271cdc0` |
| 12 | `assessments` — provider-agnostic adapter, consent gate, HMAC webhook | `8682a5a` |
| 12c (unplanned) | `identity_verification` — browser-side face-descriptor liveness + office geofence, human-review queue (ADR-007) | `06fe037` |
| 13–14 | `ee_reporting` — EEA2/EEA4 generation, approval, CSV/XLSX/PDF/XML export, equity dashboard | `056b772` |
| 15 | Employee self-service (my-profile / my-benefits / my-learning) — extends existing apps, no new app | `b5f67ce` |
| Policy section (unplanned) | `policies` — versioned policy library, acknowledgment tracking, PDF/DOCX/TXT upload + extraction + chunking seam (ADR-008) | `a5fdc7e` |
| Security pass | Trivy + ZAP; 3 real bugs fixed; CSP header; non-root Docker image | `ba75f04` |
| Step-up MFA (unplanned) | TOTP + business-justification grant gating the three Restricted-tier payroll models (ADR-009) | `0d6ea3a` |
| **16–17 Hardening & UAT** | **not started** — see §6 | — |

Demo logins (`seed_demo_data`, password = username + `123`): `hradmin`, `manager`, `recruiter`, `compmanager`,
`eemanager`, `accountingofficer`, `employee`. See `hcm/README.md` for run instructions and the full "Module rules" list.

## 3. What I would have done differently (hindsight, ranked by how much it will cost the next person)

1. **Frontend tests: there are none.** No test runner, no `test` script, no Playwright specs checked in. Every sprint was
   verified in a real browser by hand (that caught real bugs — e.g. `EEConfigurationPage` initialising `useState` from a
   still-null async prop), but nothing was captured as a repeatable script. Sprint 16–17's "full regression suite" is
   therefore mostly *frontend* work. I'd have checked in one Playwright smoke per sprint as it shipped.
2. **Celery was declared, never built.** `requirements.txt` pins `celery[redis]`, `docker-compose.yml` runs a `worker`
   service, and the README rule says "slow work runs in Celery, never in-request" — but there is **no `config/celery.py`,
   no `@shared_task`, no `.delay()` anywhere**. The worker container will crash-loop
   (`Module 'config' has no attribute 'celery'`). EE report generation, all exports, policy text extraction/chunking and
   bulk import run synchronously in the request. Either wire Celery for real or delete the worker + the two requirement
   lines + reword the rule. Don't leave it half-declared.
3. **A shared data-fetching layer in the frontend.** 29 route pages each hand-roll `useState`/`useEffect`/fetch/loading/error
   (46 effects, 37× "Loading…", 35× "Failed to load", 79× `className="form-error"`, 22 `New*Form` components of identical
   shape). A 40-line `useApiQuery`/`useMutation` hook (or TanStack Query) would delete ~1 000 lines and fix the two
   cross-cutting gaps below (no global 401 handling; no stale-response guard on most fetches) in one place.
4. **Tests + CI only ever run on SQLite; production is PostgreSQL.** The Postgres path has never been exercised by the test
   suite. Add a Postgres service job to `hcm-ci.yml` (or at least run the suite once against Docker Postgres) before UAT.
5. **Reproducible builds.** `requirements.txt` is `>=` lower bounds with no lock file; CI resolves whatever is newest each
   run (it has been fine so far because CI is green, but it *will* break one day for no code change). Add a
   `requirements.lock` / `uv lock` / `pip-compile` output.
6. **`rbac_audit` (the shared kernel) has a hard FK into `recruitment`** (`ConsentRecord.applicant`,
   `rbac_audit/models.py:155`, migration `0003` depends on `recruitment.0001`) — while `assessments` was deliberately
   contorted to *avoid* exactly that (unconstrained `applicant_id` int). The two decisions contradict each other. Pick
   one pattern and apply it to both.
7. **The README over-claims per-field tiering.** `rbac_audit/tiers.py::FIELD_TIERS` covers `Employee`, `EmployeeVersion`,
   `Applicant`, `Goal` and three `learning` models. `Review`/`Feedback` ratings, `Offer` pay fields, all of
   `compensation`, `assessments` results, biometric descriptors and `RemunerationRecord` are gated by *whole-endpoint*
   role/row checks instead. That is a defensible design (the module-rules text explains why per case), but the headline
   sentence "sensitive fields are tiered" will mislead someone adding a field to `Offer` into assuming
   `TieredModelSerializer` protects it. Reword the rule to say what actually holds.
8. **ADR files stopped at ADR-006.** ADR-007/008/009 exist only as table rows in `Architecture-Design.md §2`, not as files
   in `adr/`. Either add the three files or note in `adr/` that later ADRs live in the table.
9. **`Sprint-Plan-HCM-System.md` is 69 kB** — the status blocks are excellent but the file is now hard to onboard from.
   Sprint 0's tasks are also still all `[ ]` even though `Sprint-0-Decision-Log.md` resolves most of them. Reconcile, and
   consider moving per-sprint implementation notes into `docs/sprints/*.md` with the plan holding one-line status + link.
10. Smaller: `hcm/frontend/README.md` is the untouched Vite template; no OpenAPI schema (`api/types.ts` is a 724-line
    hand-mirror of the serializers with nothing checking it); no `LOGGING` config; `seed_demo_data.py` is 808 lines living
    in `core_hr` and importing every app (documented exception, but a `demo/` app would be cleaner);
    `fetchAllPages()` walks entire cursor-paginated collections client-side in 40+ call sites (fine at pilot scale, will
    not survive real headcount).

## 4. Concrete defects / risks found in this review (fix in Sprint 16–17)

Severity: **HIGH** = exploitable or blocks prod · **MED** = real defect · **LOW** = hygiene. All CONFIRMED by reading the code path.

| # | Sev | Finding | Where |
|---|---|---|---|
| D1 | HIGH | **No rate limiting anywhere** — not on `login_view`, not on TOTP enroll-confirm / step-up challenge. A 6-digit TOTP with `valid_window=1` (3 codes valid per 30 s) is brute-forceable without throttling. Add DRF `AnonRateThrottle`/`ScopedRateThrottle` (or django-axes) to login and both TOTP endpoints. | `rbac_audit/views.py:55-70`, `rbac_audit/stepup.py:41,58` |
| D2 | HIGH | **Celery worker cannot start** (see §3.2). | `hcm/docker-compose.yml:41`, no `config/celery.py` |
| D3 | MED | **No global 401 handling in the SPA** — `api/client.ts` throws `ApiError`, but nothing catches `status===401` to clear auth state / redirect. An expired session shows "Failed to load …" on every page instead of bouncing to login. | `frontend/src/api/client.ts:63`, `auth/AuthContext.tsx` |
| D4 | MED | **Policy upload validated by filename extension only** (`extraction.py:18`) — no content sniffing, no explicit per-file size cap beyond the global 20 MB `FILE_UPLOAD_MAX_MEMORY_SIZE`. A malformed PDF is caught by `pypdf` raising, which is fine, but a `.txt` renamed `.pdf` etc. gives a confusing error rather than a clean 400. | `policies/extraction.py`, `policies/services.py:41` |
| D5 | MED | **`RetentionRule` has no executor** — model + admin exist since Sprint 2; the scheduled job that acts on it was deferred to "post-Sprint-16 hardening" and depends on Celery beat (D2). Documented, but it's now due. | `rbac_audit/models.py:247` |
| D6 | MED | **Docker Compose has no frontend/nginx service** — ADR-005 says "nginx added at staging"; there is currently no documented way to serve the built SPA in prod, and `MEDIA_ROOT` files are only served when `DEBUG=1`. | `hcm/docker-compose.yml`, `config/settings.py` |
| D7 | MED | **`recruitment.Offer` pay fields are Restricted-tier but not step-up gated** — deliberately deferred in ADR-009 because it needs field-level rather than viewset-level gating. Still open. | `docs/sprints/step-up-authentication-payroll.md` |
| D8 | LOW | Stale comment: `rbac_audit/tiers.py:80` refers to `performance/permissions.py`, which does not exist (perf checks live in `performance/views.py`). | `rbac_audit/tiers.py:80` |
| D9 | LOW | Verbatim duplicates in the frontend: `Field` (Restricted-badge renderer) is byte-identical in `EmployeeDetailPage.tsx:14-32` and `ApplicantDetailPage.tsx:27-45`; `formatZAR` in `CompProposalsPage.tsx:5-9` and `PayBandsPage.tsx:6-10`; 27 hand-written `NavLink` entries in `AppShell.tsx:102-205` (adding a page means editing `App.tsx` + `AppShell.tsx` + role gates). | as listed |
| D10 | LOW | Test files cross the "no peer imports" boundary (`assessments/test_api.py:12` → `recruitment.models`; `ee_reporting/tests.py:8` → `learning.models`), so the rule can't be enforced with import-linter without a test carve-out. Nobody added a linter; the rule is review-only. | as listed |
| D11 | LOW | ZAP's 141 Low / 1 021 Informational alerts from the 2026-08-13 scan were never triaged (only High/Medium were). | `docs/sprints/h2-test-harness-frontend-consolidation.md` (moved to UAT-1's security pass) |

Checked and **fine** (so you don't re-check): zero `any` / non-null assertions in the frontend; `ee-reporting/constants.ts`
has not drifted from `ee_reporting/constants.py` (only display-label strings differ); zero TODO/FIXME in the codebase;
`transaction.atomic` used in every `services.py`; `select_related`/`prefetch_related` present on list endpoints; no
production-code peer-app imports except the sanctioned `learning/queries.py`; the security fixes from `ba75f04`
(`int_query_param`, authenticated media download, draft-policy visibility) are still in place; production settings flip
`SECURE_SSL_REDIRECT`/HSTS/secure cookies when `DEBUG=0`; step-up grants are per-user, scoped, 15-min, audit-logged.

## 5. Explicitly deferred items (consolidated from docs — don't lose these)

- Sprint 0 open actions: **A10** SAP/payroll interface contract (priority raised — EEA4 needs annualised remuneration);
  **A5** parallel-vs-sequential build; **A7** NFR targets; **A4** assessment-provider shortlist; DEL portal upload schema.
- ADR-004 OIDC / Entra ID SSO — **not implemented**; session auth only (`rbac_audit/views.py`).
- ADR-006 payroll sync-back to SAP; pay grade → SAP linkage.
- ADR-008 policy chatbot: embeddings, vector search, LLM, and the abuse-prevention design are all **not built**
  (seam ends at `PolicyChunk` + `GET /policies/{id}/chunks/`). No LLM integration exists anywhere in the codebase.
- ADR-009 field-level step-up for `recruitment.Offer` (D7).
- Sprint 12 optional "AI assessment recommendation / summarisation" — out of scope.
- `RetentionRule` executor (D5); Celery beat.
- Leave / time & attendance — out of scope (managed in SAP).

## 6. Recommended plan for Sprint 16–17 (Hardening & UAT)

> **Superseded 2026-08-18 by `ROADMAP-2026-08.md`** — the consolidated, sequenced plan for *everything* outstanding
> (H1–H3 hardening split, X0/PC-0…PC-3 KPI contracting per ADR-010/011 and
> `docs/superpowers/specs/2026-08-18-kpi-contracting-design.md`, C1–C7 capabilities, UAT gate). The matching
> `[ ]` backlog entries are in `docs/sprints/*.md` (linked from `Sprint-Plan-HCM-System.md`'s "Backlog additions
> 2026-08-18" table). **Start with H1.**
> The list below is kept for the reasoning behind the ordering.

Order chosen so each step de-risks the next:

1. **Decide Celery** (D2): wire `config/celery.py` + move `generate_report`/exports/extraction into tasks, *or* strip it.
   Then implement the `RetentionRule` job (D5) on whichever path you chose.
2. **Throttling** (D1) on login + TOTP endpoints; add tests that assert 429.
3. **Postgres in CI** (§3.4) + `requirements.lock` (§3.5).
4. **Frontend regression suite** (§3.1): Playwright, one spec per module, driven by the seeded demo logins — the sprint
   plan's own "Verified end-to-end in a real browser" paragraphs are effectively the test scripts, just not written down.
   Add `npm test` and a CI job. Introduce the shared fetch hook (§3.3) + global 401 handling (D3) while you're in there.
5. **RBAC penetration-style pass**: table-driven test that, for every viewset × every seeded role, asserts list/retrieve/
   create/update/delete outcomes match `RBAC-Roles.md`. Most of the pieces exist in `rbac_audit/tests.py`; make it exhaustive.
6. **Org-wide data-quality run** (`core_hr/data_quality.py`) against a full seed; **EEA export validation** against
   `EEA-Form-Spec-Notes.md` — cell-by-cell against the `.docx` layouts.
7. Docs: reconcile Sprint 0 checkboxes, add ADR-007/8/9 files, fix the README tiering sentence and the `tiers.py:80` comment,
   replace `hcm/frontend/README.md`, add nginx/frontend service to compose.
8. UAT + security/compliance sign-off need real stakeholders — prepare the walkthrough script from the sprint-plan
   verification paragraphs, but this can't be closed solo.

## 7. Missing capabilities that would benefit the current solution (not defects — gaps vs. a complete HCM)

Verified absent by grepping models/routes/views on 2026-08-18. Grouped by value; **bold** = would be expected in a
production pilot for an SA state-owned entity. Anything picked up here becomes a *new* sprint entry in
`Sprint-Plan-HCM-System.md` (unplanned addition + ADR if it changes architecture), same as 12c/Policy/Step-up did.

### 7.1 Cross-cutting platform pieces (highest leverage — every module benefits)
1. **Notifications / email (Architecture-Design gap I2/F9)** — there is no `send_mail`, no notification model, nothing.
   Every workflow that exists today (comp-proposal approval, review-cycle launch, offer acceptance, policy publish,
   liveness mismatch flagged, EE report awaiting sign-off) is silent; users must go looking. Needs an outbound email
   adapter (SMTP/Graph) + an in-app notification/"my tasks" inbox + Celery (see D2) for sending. Also unlocks
   certification-expiry, probation-end and fixed-term-contract-end reminders.
2. **Audit log viewer for the `auditor` role** — `AuditLogEntry` is written everywhere but there is **no API endpoint
   and no page**; entries are only visible in Django admin. The auditor role effectively has nothing to look at.
   Filterable list (actor, subject employee, action, tier, date range) + CSV export.
3. **Generic approvals / delegation** — approvals are hand-coded per module (comp proposal, EE report, offer). No
   "acting manager" / out-of-office delegation, so a line manager on leave blocks reviews, goals and team requests.
   A small `Delegation(from, to, scope, start, end)` honoured by `has_row_access` would cover every module at once.
4. **SSO (ADR-004, OIDC / Entra ID)** — still local username/password. Blocking for any real SOE rollout; also
   removes the need for local password policy/reset flows (which also don't exist: no password reset, no expiry).
5. **SAP payroll interface (ADR-006 / A10)** — remuneration currently arrives via CSV import only; annualised
   remuneration for EEA4 is a hard dependency. Even a scheduled read-only pull would remove a manual step.
6. **OpenAPI schema (`drf-spectacular`) + generated TS client** — replaces the 724-line hand-mirrored `api/types.ts`
   and gives integrators/UAT testers docs.
7. **Observability** — no `LOGGING`, no error tracking (Sentry), no request metrics; only `/healthz`. Needed before UAT.
8. **Backups / DR runbook** for Postgres + `MEDIA_ROOT` (policy documents are the first stored files; nothing backs them up).
9. **POPIA data-subject rights** — export-my-data / erasure request workflow, plus actually executing `RetentionRule`
   (D5). The consent plumbing exists; the subject-facing side doesn't.

### 7.2 Core HR gaps
10. **Position / establishment management** — no `Position` model: no approved-post vs. filled-post view, no vacancy
    rate, no post-numbering. For an SOE (PFMA establishment control) this is usually the first thing HR asks for;
    requisitions today are free-standing rather than tied to a vacant post.
11. **Onboarding / offboarding checklists** — `hire()` creates the employee row and `termination_reason` exists, but
    there is no task workflow (IT access, asset return, exit interview, final consent/retention state). Offboarding
    also matters for ghost-employee integrity (12c): a terminated employee should automatically drop out of liveness
    checks and role assignments.
12. **Fixed-term contract end dates + probation tracking** — `EmploymentStatus.FIXED_TERM`/`TEMPORARY`/`LEARNER`
    exist but no `contract_end_date`/`probation_end_date` fields, so nothing can warn about expiries or
    probation reviews.
13. **Employee documents** — contracts, ID copies, qualifications, disability verification: only `policies` has file
    storage. A generic `EmployeeDocument` (tiered, consent-aware, using the same authenticated `download` pattern) is
    a natural next step, and qualifications are needed for the WSP/ATR and EE reports anyway.
14. **Dependants / emergency contacts / banking details** — none modelled (banking may deliberately stay in SAP; the
    others are basic ESS expectations).
15. **Org chart visualisation + employee directory/global search** — org structure is CRUD tables; there is no
    tree/chart view and no cross-module search box.

### 7.3 Talent-module gaps
16. **Labour relations: disciplinary & grievance case management** — warnings, hearings, outcomes, CCMA referrals.
    Absent entirely; in SA public-sector HR this is a core module and it feeds EE reporting (dismissals by
    demographic in EEA2 workforce-movement section are currently only derivable from `EmploymentEvent`).
17. **Leave — read-only sync from SAP** (A6 says leave stays in SAP, but a mirror lets managers see team leave in
    the same place they approve reviews/training). Also removes the "why can't I see leave here" UAT question.
18. **Succession planning / talent pools / career paths** — no critical-post flag, no readiness rating, no successor
    lists. Ties naturally to `Position` (10) and to the skills inventory that already exists.
19. **Recruitment: interview scheduling, panel scorecards, background/reference checks, external careers portal** —
    pipeline stages exist but the interview step is a bare stage change; no external-applicant self-application.
20. **Performance: calibration/moderation step, 360° feedback, PDPs** — self + manager review only; no
    committee moderation of ratings before they feed comp proposals; no development plan object linking review
    outcomes to `learning` requests.
21. **Learning: mandatory-training compliance, course catalogue, SETA/skills-levy tracking** — training records are
    free-text; no catalogue, no "required for role" rules, no completion-rate dashboard by mandatory course.
22. **Compensation: annual salary-review / bonus cycles, total-rewards statement** — proposals are one-off; no cycle
    object to batch increases against a budget, and ESS shows benefits but not a consolidated rewards view.
23. **EE: EE plan (EEA13-style targets/barriers plan) + consultation-forum records + monitoring of numerical goals** —
    `EEPlan` exists as a model; the committee/consultation evidence trail (which the EEA2 questionnaire asks about)
    is not captured anywhere.
24. **Assessments: real provider adapter** — only the sandbox/simulated provider exists (by design, A4 open).

### 7.4 UX / non-functional
25. **Responsive/mobile layout and accessibility pass** — 6.9 kB of CSS total, desktop-only tables; ESS and
    liveness check-in are exactly the pages field staff would use on a phone.
26. **Server-side pagination/search UI** — `fetchAllPages()` everywhere; the employee list is the only page with a
    client-side filter.
27. **Bulk import/export beyond employees and remuneration** (skills, training, applicants) and a generic report
    builder / scheduled report emails (needs 1).
28. **Multilingual UI** — English only; probably acceptable for pilot, flagged for completeness.

If forced to pick three for the next unplanned sprint after Hardening: **(1) notifications + task inbox**,
**(2) audit-log viewer**, **(10) position/establishment management** — they unlock or de-risk most of the rest.

## 8. Working conventions that were in force (keep them)

- Build fully → `manage.py test` → **drive it in a real browser across every relevant role** before calling it done
  (this caught real bugs every time it was skipped) → update the sprint's `docs/sprints/*.md` status block (plus this
  file's one-line status + link in `Sprint-Plan-HCM-System.md`) + `hcm/README.md` layout/module-rules → detailed
  commit → push → next backlog item without asking.
- New module: one Django app; import only `core_hr`/`rbac_audit` (peer data via a `queries.py` seam); compose permission
  classes from `rbac_audit.permissions` primitives; sensitive models either into `FIELD_TIERS` or an explicit
  permission class with the reasoning written in the README module rules.
- Frontend: self-service pages are unrouted from `RequireRole` and self-scoped server-side; role-gated pages go under
  `RequireRole`; payroll pages wrap in `RequirePayrollStepUp`.
- Machine is unstable — persist work incrementally; commit at every green checkpoint.
