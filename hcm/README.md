# Sentech HCM — Application

Modular-monolith HCM system. Planning and architecture docs live one level up in `HR_system/`:
`Sprint-Plan-HCM-System.md` (backlog) · `Architecture-Design.md` (ADRs, module rules) · `Data-Dictionary.md` · `RBAC-Roles.md` · `Sprint-0-Decision-Log.md`.

## Layout

```
hcm/
  backend/     Django 5.2 LTS + DRF (ADR-001) — one Django app per domain module
    config/    settings, urls, wsgi/asgi, celery.py (worker/beat app; CELERY_BEAT_SCHEDULE in settings)
    core_hr/   employees, org structure, lifecycle (Sprint 1); + Sprint 3 dashboards/CRUD;
                + Sprint 15 ESS (EmployeeViewSet: PATCH own contact details, consent-gated
                self-ID via consent/self_identify actions)
    rbac_audit/ shared RBAC + audit + consent layer (Sprint 2); + Sprint 3 session auth;
                ConsentRecord extended in Sprint 4 to an employee-or-applicant subject;
                + step-up MFA (TOTPDevice/StepUpGrant, stepup.py, unplanned addition,
                ADR-009) — RFC 6238 TOTP + mandatory business-justification reason,
                required together, gating compensation.PayBand/CompProposal and
                ee_reporting.RemunerationRecord specifically (the models
                Data-Dictionary.md tiers "R"); + H1: retention.py (handler
                registry + executor for RetentionRule, tasks.py Celery task,
                `manage.py run_retention`), throttling.py (login per-IP +
                per-username, TOTP per-user rate limits); + H3 audit-log viewer
                (views.py: AuditLogEntryViewSet/audit_log_export, filterable by
                actor/action/tier/entity_type/date + CSV — AuditLogEntry itself
                is Sprint 2, was write-only/admin-only until now; its own
                `-timestamp` ordering needed a dedicated cursor pagination
                class, since the project-wide default assumes `created_at`)
    recruitment/ requisitions, applicant pipeline, offers, hire automation (Sprint 4);
                + H1 retention.py (rejected-applicant anonymise/delete handler,
                registered from apps.py); + C6 interview scheduling / panel
                scorecards / background checks / external careers portal (spec
                docs/superpowers/specs/2026-08-25-recruitment-interviews-careers-
                portal-design.md): InterviewSession (row-level read for an
                assigned interviewer, ?mine=true query param), InterviewScorecard
                (blind-review — a peer's rating/comments/recommendation stay
                hidden in to_representation until the viewer has submitted their
                own for that session), BackgroundCheck (tracking only, no vendor
                integration, IsRecruiterOrHRAdmin unchanged, no interviewer
                access at all); careers.py holds the entire public AllowAny
                surface (GET postings, POST apply) in one file deliberately, for
                auditability of the system's first anonymous-write endpoint —
                three new throttle scopes in rbac_audit/throttling.py mirror
                LOGIN_THROTTLES's shape; validation.py duplicates
                documents/validation.py's content-sniffing (peer-app boundary —
                recruitment may not import documents)
    performance/ goals, review cycles, self/manager reviews, feedback (Sprint 6);
                + PC-1 KPI contracting (ADR-010): models/ and services/ are packages
                (cycles.py = Sprint 6-7, agreements.py = periods/phases/templates/
                agreements/signatures/delegation/ReminderLog), pdf.py (the signed
                scorecard grid — its bytes are what a signature's sha256 commits to),
                reminders.py + tasks.py + `manage.py run_performance_reminders`
                (daily offsets -> collab to-dos/digests/announcements, idempotent);
                + PC-2 mid-year (Q2) + final (Q4) reviews on the same agreement/
                STAGE_FLOW state machine: q2_*/final_* AgreementElement fields
                (editable window per field — the employee's own only while that
                stage's *_open status holds, the Head's own comment stays open
                one status longer, through *_employee_signed, so the Head can
                react to what the employee just signed before signing themself),
                `EvidenceItem` (file, sniffed+hashed+authenticated download, or
                https link; "added after sign-off" stamped, never hard-deleted
                once its stage is signed), final score = Σ(weight × rating) +
                `hr_attention` computed in `_finalize_scoring`, legacy `Review`
                derived via `sync_legacy_review` when `period.legacy_cycle` is set;
                + PC-3 archive_period (permissive: FINAL_SIGNED -> ARCHIVED per
                agreement, period follows regardless of stragglers, reports
                {archived, outstanding}), rating-distribution dashboard (small-cell
                suppressed exactly like ee_reporting/core_hr's dashboards),
                `ImprovementPlan` stub behind `hr_attention` (Head/hr_admin drive
                it, never the employee it's about) — see `hcm/frontend/src/pages/
                PerformanceRecordsPage.tsx` (new, hr_admin+auditor, org-wide,
                the evidence manifest is the already-nested agreement data
                flattened, not a new model);
                + C6 calibration/moderation + 360 feedback (spec docs/superpowers/
                specs/2026-08-25-performance-calibration-360-design.md): two new
                sibling model modules, calibration.py (CalibrationSession scoped
                by period x department, blank department = org-wide, reusing the
                rating-distribution dashboard's own grouping; CalibrationAdjustment
                create-only, reason required even for "no change", never triggers
                amend_agreement's re-sign — a consistency check layered on top of
                an already-signed agreement, not a renegotiation; three
                independent audit trails — the adjustment row, PerformanceAgreement.
                history via the existing simple_history middleware, and log_access)
                and feedback360.py (Feedback360Request/Rater/Response, attached to
                PerformanceAgreement not the legacy free-text Feedback model;
                self/manager raters automatic, peer/direct_report nominated +
                Head/hr_admin-approved; relationship derived server-side from the
                org chart, same pattern classify_feedback_type already uses). The
                load-bearing decision is visibility (spec §2.10): Head/hr_admin/
                auditor and a rater's own row see full attribution always; the
                subject sees self/manager in full but peer/direct-report only as a
                pooled ratings-only average once >=3 responses exist per
                relationship bucket (FEEDBACK_360_MIN_RESPONSES_FOR_AGGREGATE = 3,
                deliberately not views_agreements.SMALL_CELL_THRESHOLD's 5 — a
                different risk shape/scale), never with free text. Never an input
                to final_score. New routes: `/calibration` (hr_admin), embedded
                Feedback360Section on the existing agreement card, and
                `/my-feedback-requests` (roles: [], ?mine=true — same shape
                InterviewSession's ?mine=true already uses for panelists)
    learning/  skills, certifications, training records, WSP/ATR export (Sprint 8);
                + Sprint 15 ESS (TrainingRecord.Status.REQUESTED — self-submitted
                enrollment requests, forced status/field restrictions);
                + C6 mandatory-training compliance (spec docs/superpowers/specs/
                2026-08-25-mandatory-training-compliance-design.md): Course
                catalogue + CourseRequirement (scoped by Department/
                OccupationalLevel, both optional — job_title/Position/job_grade
                considered and rejected, see spec §2.3), TrainingRecord.course
                (nullable FK, no backfill onto historical rows). Compliance is
                derived on read (compliance.py), never stored — same philosophy
                as establishment.Position.current_occupant. Aggregate
                completion-rate dashboard is hr_admin-only; the named
                overdue-individuals list is row-scoped via the existing
                row_scoped_queryset primitive (own reporting chain, or org-wide
                for an all-scope role) — no new access-control mechanism.
                MANDATORY_TRAINING_OVERDUE registered into core_hr's
                data-quality sweep; a daily Celery task reuses notifications.
                services.notify/notify_many for due/overdue reminders.
    compensation/ pay bands, comp proposal workflow, benefits catalog + elections (Sprint 10);
                + Sprint 15 ESS (benefits catalog read-open, elections self-service
                row-scoped); + C6 salary-review/bonus cycles (CompCycle, budget
                utilization derived live + row-locked against the create/approve race,
                not step-up-gated unlike PayBand/CompProposal) and GET /my-total-rewards/
                (a new, narrow self-only view spanning ee_reporting's RemunerationRecord
                via a new queries.py seam, own pay-band position, own benefits, and
                performance's existing latest_final_score seam — never any CompProposal;
                spec docs/superpowers/specs/2026-08-26-salary-review-cycles-total-
                rewards-design.md)
    assessments/ provider-agnostic assessment adapter, consent-gated assign workflow,
                HMAC-signed inbound webhook (Sprint 12); applicant_id is an unconstrained
                reference, not a cross-app FK — see Module rules below
    identity_verification/ ghost-employee mitigation: client-side face-descriptor
                enrollment/verification (no biometric vendor — face-api.js runs in the
                browser) + office-attendance geofence check (Sprint 12c, unplanned
                addition; see ADR-007 in Architecture-Design.md)
    ee_reporting/ EEA2/EEA4 draft generation, approval workflow, CSV/Excel/PDF/XML
                export, equity dashboard (Sprint 13-14); field/category lists extracted
                verbatim from the official form documents into constants.py; reads
                learning data via learning/queries.py, not a direct model import —
                see Module rules below
    integrations/ outbound adapters (ADR-011): collab.py (httpx client to the collab
                platform's /integrations surface — work-item upsert/close, announcements,
                identity lookups; retries; None when COLLAB_ENABLED is off), sync.py +
                `manage.py sync_collab_ids` (Employee.collab_user_id / Department.
                collab_department_id by email/name), tasks.py. Imports core_hr only.
    policies/  HR policy document library + versioning + acknowledgment tracking
                (Policy section, unplanned addition, ADR-008); document upload with
                PDF/DOCX/TXT text extraction (extraction.py) and a deterministic
                paragraph/sentence-aware chunking pipeline (chunking.py) — the seam
                a future RAG/chatbot phase would embed and retrieve over; no
                embeddings, vector search, or LLM integration exist yet (deliberately
                deferred — see ADR-008)
    notifications/ in-app + email notifications (H3): models.py::Notification,
                services.py::notify/notify_many/employees_with_role — the one write
                path every consumer uses (PC reminders, comp approvals, review
                launch, policy publish, liveness flag, EE sign-off); email is
                best-effort on top of an always-created in-app row (SMTP via
                EMAIL_* settings, console backend when SMTP_HOST is unset).
                Shared kernel (like integrations): imports core_hr only, knows
                recipients and message text, nothing about any domain
    onboarding/ onboarding/offboarding checklists (C1 part 3 slice 3, spec
                docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md):
                versioned ChecklistTemplate/ChecklistTemplateItem (flat ordered
                task list, no signing/scoring — deliberately simpler than
                performance.AgreementTemplate) and ChecklistInstance/
                ChecklistInstanceItem, which snapshot a template's items at
                creation. Triggered automatically off core_hr.Employee.hire()
                and off an ending-type EmploymentChange executing, via a new
                core_hr/lifecycle_hooks.py registry (same shape as
                access_cascade.py/data_quality.py) — core_hr is SHARED_KERNEL
                and never imports this app.
    documents/ employee documents & POPIA data-subject rights (C2, spec
                docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md):
                EmployeeDocument (tier is a document_type-driven row-level
                property, not a rbac_audit/tiers.py field entry — sensitivity
                varies by row, not by field; content-sniffed upload via
                validation.py, same fix policies/extraction.py established;
                authenticated download reuses PolicyViewSet.download's exact
                FileResponse pattern) and DataSubjectRequest (export/erasure
                workflow, hr_admin-reviewed, never auto-executed — erasure is
                a hardcoded allow-list, never a RetentionRule-driven delete,
                so it can never reach employment history/audit logs). New
                core_hr models Dependant/EmergencyContact ride alongside
                (self-or-hr_admin only, third-party data).
    succession/ succession planning / talent pools (C6, second sub-item, spec
                docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md):
                CriticalPost (OneToOneField flag on establishment.Position,
                active toggles it without deleting) and SuccessionCandidate
                (nominee + readiness: ready_now/ready_1_2_years/
                ready_3_plus_years/development_needed). Not SHARED_KERNEL —
                reads establishment.Position/core_hr.Employee directly (both
                kernel) but nothing needs a reverse FK into it. No
                services.py — every write is single-row, validated in the
                serializer, matching Skill/Course/CourseRequirement's shape
                rather than Position's/ChecklistTemplate's workflow shape.
                Read access to the successor-candidate list is hr_admin/
                auditor only, with NO self-scope carve-out anywhere — the
                viewset's own get_queryset excludes the acting requester's
                own employee_id regardless of role, so not even an hr_admin
                can see their own row. The critical-post flag itself is
                visible to the same audience Position already is. Adds
                learning/queries.py::skill_names_for_employee and a new
                performance/queries.py::latest_final_score (performance's
                first read seam) as read-only informational context on a
                candidate's card — never an input to the stored readiness
                value. CRITICAL_POST_NO_SUCCESSOR registered into core_hr's
                data-quality sweep (an active critical post with no active
                ready-now/ready-soon candidate, attached to its current
                occupant; a vacant critical post is silently skipped).
  frontend/    React 19 + TypeScript (Vite) + React Router
    auth/      session login/logout, route guards; RequirePayrollStepUp.tsx —
               TOTP enrollment + step-up challenge UI, a children-wrapper (not a
               route-Outlet guard like RequireRole) around PayBandsPage,
               CompProposalsPage, and just the remuneration sub-section of
               EEConfigurationPage
    pages/     employee list/detail, org structure, data quality, headcount dashboard
               (Sprint 3); requisitions, applicants, recruitment dashboard (Sprint 4);
               review cycles, reviews (Sprint 6); skills inventory, team development
               (Sprint 8 — skills/certs/training live on employee detail, like goals/feedback);
               pay bands, comp proposals, benefits (Sprint 10 — comp_manager/hr_admin only);
               employee assessments (Sprint 12 — ee_manager/hr_admin only; applicant-subject
               assessments live on ApplicantDetailPage instead, like Offer); my-verification
               (Sprint 12c — every employee) + workforce-integrity (hr_admin's review queue);
               EE configuration, EE reports, equity dashboard (Sprint 13-14 —
               hr_admin/ee_manager/accounting_officer/auditor only); my-profile,
               my-benefits, my-learning (Sprint 15 — every employee, self-scoped
               server-side, same unrouted-from-RequireRole shape as my-verification);
               policies (hr_admin-only library + upload/publish workflow),
               dashboards/policy-acknowledgment (hr_admin-only compliance %),
               my-policies (every employee — read + acknowledge, Policy section);
               my-documents (C2 — every employee: documents, dependants,
               emergency contacts, POPIA export/erasure requests, one
               combined self-service page); Documents/Dependants/Emergency
               Contacts sections on EmployeeDetailPage (hr_admin manages
               anyone's, same page self reaches for their own); hr_admin +
               auditor data-subject-requests review queue (auditor read-only
               — action buttons hidden client-side, 403'd server-side);
               talent-pools (C6, hr_admin-only — flag a critical post,
               nominate/rate/withdraw successor candidates); Positions page
               gains a Critical column; EmployeeDetailPage gains a read-only
               Succession section, hr_admin/auditor-only and never fetched
               for your own record (the backend's own self-exclusion is the
               real guarantee, not this client-side skip); C6 interview
               scheduling/scorecards/background checks — ApplicantDetailPage
               gains Interviews (schedule a session, panel picker, per-session
               scorecard aggregate) and Background checks sections; new
               my-interviews (every employee — being tapped as a panelist is
               row-level, not tied to any role; own assigned sessions +
               scorecard submission, with blind-review masking rendered
               client-side from what the API already omits); ApplicantsPage
               gains a Source column (Careers site / Internal). C6 careers
               portal — CareersListPage (/careers) and CareersPostingPage
               (/careers/:id), the SPA's only routes genuinely outside
               RequireAuth/AppShell (no session, no session-driven nav);
               RequisitionsPage gains a description field + a "post to the
               public careers site" toggle per requisition; C6 calibration +
               360 feedback — new CalibrationPage (/calibration, hr_admin-only:
               pick a period, open a session, record an outcome per agreement
               in the cohort, close it); a Feedback360Section embedded on the
               existing agreement card (MyPerformancePage/TeamPerformancePage)
               for open/nominate/approve/decline/view, with server-enforced
               masking rendered client-side purely from what the API omits
               (never reimplemented in the component); new
               MyFeedbackRequestsPage (/my-feedback-requests, every employee,
               ?mine=true — the one place any rater, including the subject's
               own self-assessment and the Head's own manager response,
               actually answers). MyPerformancePage also gained a real fix
               along the way: every past year now gets an Open/Viewing toggle
               into the full agreement card (previously only the most recent
               year did) — calibration outcomes and 360 rounds can exist on an
               older, already-archived agreement, not just the current one
    liveness/  face-api.js wrapper + shared camera-capture component (Sprint 12c);
               lazy-loaded (React.lazy) since TensorFlow.js is ~1MB and only this
               one page needs it
    ee-reporting/ constants.ts (manual mirror of the backend's constants.py — not
               auto-synced) + MatrixTable.tsx, the shared level x demographic-column
               table renderer used by the EE config/reports/dashboard pages (Sprint 13-14)
    components/ small pieces shared across pages (e.g. the dashboard Breakdown chart)
    api/       fetch client (CSRF-aware, global session-expiry handling) + shared
               reference-data context; hooks.ts — useApiQuery/useAllPages/useMutation
               (H2: the one place loading/error/stale-response state lives);
               + H3: generated-types.ts (OpenAPI-generated, not yet consumed by any
               page — see `npm run generate:api-types` below; types.ts is still the
               real source of truth for now)
    layout/    AppShell + navConfig.ts (nav as data with role gates)
    lib/       small pure helpers (formatZAR)
  frontend/tools/api-codegen/  isolated devDependency scope (H3), pinned to
               TypeScript 5 — openapi-typescript 7.x calls the TS compiler API
               directly and breaks under this project's TypeScript 7; see the
               comment in scripts/generate-api-types.mjs for the full story.
               `npm run generate:api-types` (from hcm/frontend) regenerates
               src/api/generated-types.ts from the live Django schema.
  frontend/e2e/ Playwright suite (H2): 23 real-browser tests over a throwaway seeded
               Django (e2e/backend-server.mjs) + Vite dev server — `npm test`
  docker-compose.yml  db + redis + backend + celery worker + beat + frontend (nginx SPA +
                reverse proxy, port 8080) (ADR-005); frontend/Dockerfile + nginx.conf;
                + H3: backend's Dockerfile HEALTHCHECK polls /readyz (stdlib urllib, no
                curl in python:3.13-slim), frontend now waits on backend: service_healthy
```

**Ops (H3):** `/healthz` is process-up only (load-balancer liveness); `/readyz` checks
DB + cache and is what Docker's `HEALTHCHECK` / an orchestrator's readiness probe should
point at instead. `LOGGING` is plain stdlib-to-stderr (`DJANGO_LOG_LEVEL` to tune).
Sentry (`sentry-sdk`) is opt-in via `SENTRY_DSN` — unset by default everywhere, `sentry_sdk`
imported only inside that guard so nothing needs it installed to boot; `send_default_pii=False`
always (POPIA). Backup/restore procedures (concrete `pg_dump`/`pg_restore`/media-volume
commands, a restore-rehearsal checklist) live in `docs/RUNBOOK.md`, not just referenced
as policy in ADR-005. `/api/schema/` (raw OpenAPI JSON) and `/api/docs/` (Swagger UI) are
hr_admin-only (`IsHRAdminSchema`) — developer/ops tooling, not an employee-facing surface.

## Local development

Backend (SQLite fallback — no services needed):

```powershell
cd backend
python -m venv .venv            # NOTE: prefer a venv OUTSIDE OneDrive (see below)
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_demo_data   # synthetic org + employees + demo logins (local dev only)
.venv\Scripts\python manage.py runserver   # http://localhost:8000/healthz
```

Demo logins from `seed_demo_data` (password = username + "123"): `hradmin` (HR Admin),
`hradmin2` (a second HR Admin — needed for the exit state machine's tiered
"a different hr_admin must confirm" control, C1 part 3; with only one hr_admin seeded
every tiered change would be proposable but never confirmable), `manager` (Line Manager),
`recruiter` (Recruiter), `compmanager` (Compensation Manager),
`eemanager` (EE Manager), `accountingofficer` (Accounting Officer/CEO, EEA2/EEA4
sign-off only — Sprint 13-14), `auditor` (Auditor, read-only everywhere — added PC-3;
reports to nobody in the org chart, same as the CEO, since an auditor's read access
spans every department), `employee` (Employee, self-scope only). Every login can
reach the Sprint 15 self-service pages (my-profile/my-benefits/my-learning) for their
own record — `employee`'s own contact details/self-ID are left deliberately unset by
the seed script so there's something real to fill in on first login. Every login can
also reach my-policies; `hradmin` additionally sees the Policy Library and Policy
Compliance dashboard, seeded with a mix of published (varied acknowledgment %) and
one draft policy left unpublished for a live demo.

No demo login starts with a TOTP device enrolled (ADR-009) — `pay-bands`,
`comp-proposals`, and EE Configuration's Remuneration Records section all show a
live step-up-authentication challenge (enroll → confirm → verify + justify) on
first visit for `compmanager`/`hradmin`, deliberately, so there's always something
real to demo for that capability rather than a pre-satisfied gate.

`onboarding`'s "Standard onboarding"/"Standard offboarding" checklist templates are
seeded and published before any employee is hired, so every seeded employee already
has an onboarding checklist at `/checklists` (`hradmin` sees them all; `manager` sees
`employee`'s; `employee` sees only their own — see RBAC-Roles.md). A couple of
`employee`'s onboarding tasks are pre-completed so the page shows a mix of done/not-done,
and one throwaway employee is hired and immediately resigned so a real offboarding
checklist exists too, created automatically the moment the exit executes.

`identity_verification`'s face-descriptor model weights are checked into
`frontend/public/models/` (copied from `node_modules/@vladmandic/face-api/model/` —
TinyFaceDetector + FaceLandmark68 + FaceRecognition, ~7MB total), so no extra
download step is needed for local dev. `/my-verification` needs real camera
(and ideally geolocation) permission in the browser to do anything useful.

`policies.Policy.source_file` is this codebase's first use of file storage —
uploaded PDF/DOCX/TXT policy documents are saved under `MEDIA_ROOT` (`backend/media/`,
gitignored, served by Django itself only when `DEBUG=1`; production would point this
at S3/Azure Blob instead, per ADR-005's deferral pattern). No extra setup needed
locally — Django's storage backend creates `media/` itself on the first upload.

Frontend — the Vite dev server proxies `/api` and `/admin` to `localhost:8000`
(`vite.config.ts`), so run both at once:

```powershell
cd frontend
npm install
npm run dev   # http://localhost:5173
```

If the backend runs on a different origin than `localhost:5173`/`127.0.0.1:5173`,
set `DJANGO_CSRF_TRUSTED_ORIGINS` (see `.env.example`) or mutating requests
(login excepted) will 403 with a CSRF Origin-check failure.

Full stack via Docker (PostgreSQL + Redis + worker + beat + nginx frontend on http://localhost:8080):

```powershell
copy .env.example .env   # then edit secrets (DJANGO_SECURE_SSL_REDIRECT=0 for plain-http LAN use)
docker compose up --build
docker compose exec backend python manage.py seed_demo_data
```

Backend Python deps are pinned in `backend/requirements.lock` (pip-compile output of
`requirements.txt`; regenerate with `pip-compile --strip-extras --output-file requirements.lock requirements.txt`
after editing `requirements.txt`). Retention rules run daily via Celery beat; `manage.py run_retention --dry-run`
shows what they would do.

> **OneDrive note:** this folder syncs to OneDrive. Keep `node_modules/` and
> Python venvs out of it where possible (both are gitignored, but OneDrive
> still syncs them): create the venv at e.g. `%LOCALAPPDATA%\venvs\hcm` and
> consider marking `node_modules` as "always keep on this device only", or
> develop via Docker.

## Module rules (enforced in review — see Architecture-Design.md §4)

- Apps may import `core_hr` and `rbac_audit`; apps may **not** import each other.
  (`core_hr/management/commands/seed_demo_data.py` is the one intentional exception —
  it seeds demo data across every module for local dev/UI review, not core_hr logic,
  so it imports `recruitment` too; noted inline where it does.) This shapes schema
  design, not just imports: `assessments.AssessmentAssignment` needs an employee-or-
  applicant subject but must not import `recruitment.Applicant`, so `applicant_id` is
  a plain unconstrained integer rather than a cross-app FK (safe in practice —
  `recruitment.Applicant` rows are never hard-deleted). Applicant-subject consent
  capture likewise goes through recruitment's own `/applicants/{id}/consent/`
  endpoint (generalized with a `purpose` field) rather than being duplicated in
  `assessments`, which only ever reads whether consent already exists.
  `ee_reporting` needs learning-module data (completed training, for the Skills
  Development section) without importing `learning.models` directly — it goes
  through `learning/queries.py`, a small read-only query-interface module that
  exists purely to be imported by other apps, per Architecture-Design.md §4's
  own named example of how the "no peer imports" rule is meant to be satisfied.
  `succession` (C6) is the first consumer to need this pattern twice at once —
  it reads `learning/queries.py::skill_names_for_employee` and a new
  `performance/queries.py::latest_final_score` (performance's first read seam)
  as informational context on a successor candidate's card, never as an input
  to the stored readiness value. `succession` itself imports `establishment`
  and `core_hr` directly rather than through a seam — both are `SHARED_KERNEL`
  (below), which any domain app may import freely; `succession` does not join
  the kernel itself, since nothing needs a reverse FK into it. C6's
  salary-review cycles need "this employee's current actual salary" --
  per ADR-006/`compensation.PayBand`'s own docstring, that fact lives in
  `ee_reporting.RemunerationRecord`, not `compensation`'s own models -- so
  `compensation` reads it through a new `ee_reporting/queries.py::
  latest_remuneration_for_employee` (ee_reporting's first read seam),
  both from `compensation/services.py` (a cycle-attached increase
  proposal's budget baseline) and from `compensation/views.py`'s new
  `GET /my-total-rewards/` (see RBAC-Roles.md for that endpoint's
  self-scope boundary). The same view reuses `performance/queries.py::
  latest_final_score` a second time (succession was its first caller) as
  read-only context on a `CompProposal` and on the total-rewards
  statement -- never an input to any amount.
- All API access goes through the shared RBAC permission classes + field-tier
  serializer mixin from `rbac_audit` (Sprint 2). No per-module access control.
- Background/scheduled work runs in Celery (`config/celery.py`; worker + beat
  services in docker-compose; eager in-process when `REDIS_URL` is unset so
  dev/tests need no broker). Scheduled jobs live in `CELERY_BEAT_SCHEDULE`
  (`config/settings.py`) and task modules in `<app>/tasks.py` — first one is
  `rbac_audit.tasks.run_retention_task` (H1). Report generation, exports and
  document extraction still run in-request today; move them to tasks when
  their runtime warrants it, not before.
- Sensitive fields (race, gender, disability, pay, ratings, assessment results)
  are classified per `Data-Dictionary.md` — hard constraint from the sprint plan.
  **How that is enforced differs by model, and you must check which applies
  before adding a field:** `rbac_audit/tiers.py::FIELD_TIERS` (per-field
  redaction through `TieredModelSerializer`) covers `core_hr.Employee`/
  `EmployeeVersion`, `recruitment.Applicant`, `performance.Goal` and the
  `learning` models only. `performance.Review`/`Feedback` ratings,
  `recruitment.Offer` pay fields, all of `compensation`, `assessments`
  results, `identity_verification` biometrics and `ee_reporting.
  RemunerationRecord` are gated at the *endpoint* level by row-scope or an
  explicit permission class instead (reasons per case below) — a new field on
  one of those models is NOT protected by the tier map, only by that
  endpoint's gate.
- A role's field-tier grant only applies within that role's own row-scope
  (`can_access_tier_for_target`) — the base self-scope `employee` role granting
  Sensitive-tier read for one's own record must never leak onto records reached
  via a different, wider-scoped role the same person holds. Found as a real bug
  during Sprint 3 browser verification; see the sprint plan's Sprint 3 entry.
- Not every Sensitive-tier model should use the generic tiered-serializer path:
  where a role's row-scope legitimately grants individual access the role's own
  blanket tier grant doesn't cover (line_manager on `performance.Review`,
  recruiter on `recruitment.Offer`'s pay fields, comp_manager across the whole
  `compensation` module), gate on row-scope (`RowScopePermission`) or a
  dedicated role-check permission class alone instead of forcing the mismatch
  through `can_access_tier_for_target`. `assessments.AssessmentAssignment` goes
  further still — its two subject types (employee vs. applicant) have
  genuinely different access rules, not just a row-scope mismatch, so it skips
  the generic helpers entirely in favour of an explicit permission class
  (`assessments/permissions.py::CanAccessAssessmentAssignment`).
  `identity_verification` does the same for a different reason: biometric data
  doesn't fit the generic P/I/S/R tiers at all (POPIA treats it as a stricter
  category than this system's highest generic tier) — see
  `identity_verification/permissions.py::IsSelfOrHRAdmin`.
  `ee_reporting` follows the same shape: `EEReportingPermission` is a coarse
  "holds some EE-reporting role" gate at the DRF level, with the real
  distinctions (hr_admin-only writes; ee_manager's review step; the
  accounting_officer's sign-off step) enforced by explicit `has_role()` checks
  inside the specific view methods — a permission class that tried to
  encode all of that itself silently 403'd the ee_manager/accounting_officer
  steps in this sprint's own testing (see the sprint plan's Sprint 13-14 entry).
  `accounting_officer` (row_scope=all, no generic P/I/S/R grants — mirrors
  `sysadmin`) can read/sign full report snapshots but is still subject to
  small-cell suppression on the *live* Equity Dashboard, since that check
  requires an explicit sensitive-tier grant the role deliberately doesn't have.
- Row-scope coverage (who can *see* a record via `RowScopePermission`) is not
  the same set as who should be able to *write* to it — Sprint 15 (ESS) is
  the first module to layer a real write onto an already-read-only, row-
  scoped endpoint (`core_hr.EmployeeViewSet`) without a bespoke permission
  class for it. Every all/own_team-scope role (auditor, line_manager) can
  already *read* any employee's record; `EmployeeSerializer.validate()`, not
  the permission class, is where "self or hr_admin only, ESS-editable fields
  only" is actually enforced. The same shape appears in
  `learning.TrainingRecordSerializer.validate()` (a self-submission is
  server-forced to `REQUESTED`, stripped of `hours`/`cost`/
  `completion_date`, and can't later self-edit those) and
  `compensation.BenefitsElectionViewSet.perform_create()` (non-privileged
  callers can only ever create a row for themselves, regardless of what
  `employee` id the client sends).
- `policies` follows `identity_verification`'s "no vendor under contract yet"
  pattern for two separate things at once (ADR-008): no biometric-style
  vendor risk applies here, but no LLM vendor is under contract either, and
  wiring one is a real per-query cost + an abuse-prevention design that
  needs sign-off before it ships — not something to bolt on incidentally
  because the plumbing (`policies/chunking.py`) happened to get built.
  `PolicyChunk` rows exist and are inspectable (`GET /policies/{id}/chunks/`)
  precisely so that seam is real and tested now, without pretending the
  retrieval/chatbot layer on top of it exists yet.
- Performance agreements (PC-1) use an explicit permission class
  (`performance/permissions.py`), like `assessments`/`ee_reporting`: the Head
  is *snapshotted* on the agreement and may be substituted by an active
  `SigningDelegation`, neither of which is expressible as a row-scope rule.
  Two rules worth keeping in mind when extending it: a **detail** route must
  not pre-filter the queryset (the object permission decides — pre-filtering
  ran a reporting-chain walk per row and stalled the UI), and a request for
  someone else's agreement answers **404, not 403**, so it doesn't confirm the
  record exists.
- `integrations` is **shared infrastructure**, not a domain app: any module may
  import it (the module-boundary test lists it in SHARED_KERNEL), on the
  condition that it stays domain-agnostic — it knows about work items and
  announcements, never about agreements. PC-1's reminder job composes the
  titles, external refs and deep links; the adapter just delivers them.
- `RequiresPayrollStepUp` (ADR-009) is layered ON TOP OF a module's normal
  role-based permission class in `permission_classes` — DRF requires every
  listed class to pass, so this doesn't replace
  `compensation.IsCompManagerOrHRAdmin`/`ee_reporting.EEReportingPermission`,
  it adds a second, narrower bar for the three Restricted-tier payroll
  models specifically. Only apply it to a whole viewset when every field on
  that model is genuinely payroll data — `recruitment.Offer` is also "R"
  but mixed with non-pay fields, which is why it's explicitly NOT gated
  this way (see the sprint plan's own entry for the reasoning); a
  field-level version of this pattern is the right follow-up there, not a
  copy-paste of the viewset-level one.

## CI

`.github/workflows/hcm-ci.yml` (repo root): backend job (SQLite: checks +
missing-migration guard + Celery smoke + tests), backend-postgres job (Postgres 17:
migrate + seed_demo_data + tests), frontend job (typecheck/lint/build), e2e job
(Playwright against seeded Django + Vite, report artifact). Backend guard-rail
tests worth knowing: `rbac_audit/test_access_matrix.py` (golden role x endpoint
matrix — a deliberate permission change means editing `EXPECTED` and saying why)
and `rbac_audit/test_module_boundaries.py` (the "no peer imports" rule, enforced).
