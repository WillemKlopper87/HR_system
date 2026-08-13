# Sentech HCM — Application

Modular-monolith HCM system. Planning and architecture docs live one level up in `HR_system/`:
`Sprint-Plan-HCM-System.md` (backlog) · `Architecture-Design.md` (ADRs, module rules) · `Data-Dictionary.md` · `RBAC-Roles.md` · `Sprint-0-Decision-Log.md`.

## Layout

```
hcm/
  backend/     Django 5.2 LTS + DRF (ADR-001) — one Django app per domain module
    config/    settings, urls, wsgi/asgi
    core_hr/   employees, org structure, lifecycle (Sprint 1); + Sprint 3 dashboards/CRUD;
                + Sprint 15 ESS (EmployeeViewSet: PATCH own contact details, consent-gated
                self-ID via consent/self_identify actions)
    rbac_audit/ shared RBAC + audit + consent layer (Sprint 2); + Sprint 3 session auth;
                ConsentRecord extended in Sprint 4 to an employee-or-applicant subject
    recruitment/ requisitions, applicant pipeline, offers, hire automation (Sprint 4)
    performance/ goals, review cycles, self/manager reviews, feedback (Sprint 6)
    learning/  skills, certifications, training records, WSP/ATR export (Sprint 8);
                + Sprint 15 ESS (TrainingRecord.Status.REQUESTED — self-submitted
                enrollment requests, forced status/field restrictions)
    compensation/ pay bands, comp proposal workflow, benefits catalog + elections (Sprint 10);
                + Sprint 15 ESS (benefits catalog read-open, elections self-service
                row-scoped)
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
    policies/  HR policy document library + versioning + acknowledgment tracking
                (Policy section, unplanned addition, ADR-008); document upload with
                PDF/DOCX/TXT text extraction (extraction.py) and a deterministic
                paragraph/sentence-aware chunking pipeline (chunking.py) — the seam
                a future RAG/chatbot phase would embed and retrieve over; no
                embeddings, vector search, or LLM integration exist yet (deliberately
                deferred — see ADR-008)
  frontend/    React 19 + TypeScript (Vite) + React Router
    auth/      session login/logout, route guards
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
               my-policies (every employee — read + acknowledge, Policy section)
    liveness/  face-api.js wrapper + shared camera-capture component (Sprint 12c);
               lazy-loaded (React.lazy) since TensorFlow.js is ~1MB and only this
               one page needs it
    ee-reporting/ constants.ts (manual mirror of the backend's constants.py — not
               auto-synced) + MatrixTable.tsx, the shared level x demographic-column
               table renderer used by the EE config/reports/dashboard pages (Sprint 13-14)
    components/ small pieces shared across pages (e.g. the dashboard Breakdown chart)
    api/       fetch client (CSRF-aware) + shared reference-data context
  docker-compose.yml  db + redis + backend + celery worker (ADR-005)
```

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
`manager` (Line Manager), `recruiter` (Recruiter), `compmanager` (Compensation Manager),
`eemanager` (EE Manager), `accountingofficer` (Accounting Officer/CEO, EEA2/EEA4
sign-off only — Sprint 13-14), `employee` (Employee, self-scope only). Every login can
reach the Sprint 15 self-service pages (my-profile/my-benefits/my-learning) for their
own record — `employee`'s own contact details/self-ID are left deliberately unset by
the seed script so there's something real to fill in on first login. Every login can
also reach my-policies; `hradmin` additionally sees the Policy Library and Policy
Compliance dashboard, seeded with a mix of published (varied acknowledgment %) and
one draft policy left unpublished for a live demo.

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

Full stack via Docker (PostgreSQL + Redis + worker):

```powershell
copy .env.example .env   # then edit secrets
docker compose up --build
```

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
- All API access goes through the shared RBAC permission classes + field-tier
  serializer mixin from `rbac_audit` (Sprint 2). No per-module access control.
- Slow work (imports, report generation, webhooks) runs in Celery, never in-request.
- Sensitive fields (race, gender, disability, pay, ratings, assessment results)
  are tiered per `Data-Dictionary.md` — hard constraint from the sprint plan.
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

## CI

`.github/workflows/hcm-ci.yml` (repo root): Django checks + missing-migration
guard + tests; frontend typecheck/lint/build. The Sprint 2 RBAC regression
suite becomes the baseline every module sprint extends.
