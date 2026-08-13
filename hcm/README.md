# Sentech HCM — Application

Modular-monolith HCM system. Planning and architecture docs live one level up in `HR_system/`:
`Sprint-Plan-HCM-System.md` (backlog) · `Architecture-Design.md` (ADRs, module rules) · `Data-Dictionary.md` · `RBAC-Roles.md` · `Sprint-0-Decision-Log.md`.

## Layout

```
hcm/
  backend/     Django 5.2 LTS + DRF (ADR-001) — one Django app per domain module
    config/    settings, urls, wsgi/asgi
    core_hr/   employees, org structure, lifecycle (Sprint 1); + Sprint 3 dashboards/CRUD
    rbac_audit/ shared RBAC + audit + consent layer (Sprint 2); + Sprint 3 session auth;
                ConsentRecord extended in Sprint 4 to an employee-or-applicant subject
    recruitment/ requisitions, applicant pipeline, offers, hire automation (Sprint 4)
    performance/ goals, review cycles, self/manager reviews, feedback (Sprint 6)
    learning/  skills, certifications, training records, WSP/ATR export (Sprint 8)
    compensation/ pay bands, comp proposal workflow, benefits catalog + elections (Sprint 10)
    assessments/ provider-agnostic assessment adapter, consent-gated assign workflow,
                HMAC-signed inbound webhook (Sprint 12); applicant_id is an unconstrained
                reference, not a cross-app FK — see Module rules below
    identity_verification/ ghost-employee mitigation: client-side face-descriptor
                enrollment/verification (no biometric vendor — face-api.js runs in the
                browser) + office-attendance geofence check (Sprint 12c, unplanned
                addition; see ADR-007 in Architecture-Design.md)
  frontend/    React 19 + TypeScript (Vite) + React Router
    auth/      session login/logout, route guards
    pages/     employee list/detail, org structure, data quality, headcount dashboard
               (Sprint 3); requisitions, applicants, recruitment dashboard (Sprint 4);
               review cycles, reviews (Sprint 6); skills inventory, team development
               (Sprint 8 — skills/certs/training live on employee detail, like goals/feedback);
               pay bands, comp proposals, benefits (Sprint 10 — comp_manager/hr_admin only);
               employee assessments (Sprint 12 — ee_manager/hr_admin only; applicant-subject
               assessments live on ApplicantDetailPage instead, like Offer); my-verification
               (Sprint 12c — every employee) + workforce-integrity (hr_admin's review queue)
    liveness/  face-api.js wrapper + shared camera-capture component (Sprint 12c);
               lazy-loaded (React.lazy) since TensorFlow.js is ~1MB and only this
               one page needs it
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
`eemanager` (EE Manager), `employee` (Employee, self-scope only).

`identity_verification`'s face-descriptor model weights are checked into
`frontend/public/models/` (copied from `node_modules/@vladmandic/face-api/model/` —
TinyFaceDetector + FaceLandmark68 + FaceRecognition, ~7MB total), so no extra
download step is needed for local dev. `/my-verification` needs real camera
(and ideally geolocation) permission in the browser to do anything useful.

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

## CI

`.github/workflows/hcm-ci.yml` (repo root): Django checks + missing-migration
guard + tests; frontend typecheck/lint/build. The Sprint 2 RBAC regression
suite becomes the baseline every module sprint extends.
