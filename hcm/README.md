# Sentech HCM — Application

Modular-monolith HCM system. Planning and architecture docs live one level up in `HR_system/`:
`Sprint-Plan-HCM-System.md` (backlog) · `Architecture-Design.md` (ADRs, module rules) · `Data-Dictionary.md` · `RBAC-Roles.md` · `Sprint-0-Decision-Log.md`.

## Layout

```
hcm/
  backend/     Django 5.2 LTS + DRF (ADR-001) — one Django app per domain module
    config/    settings, urls, wsgi/asgi
    core_hr/   employees, org structure, lifecycle (Sprint 1); + Sprint 3 dashboards/CRUD
    rbac_audit/ shared RBAC + audit + consent layer (Sprint 2); + Sprint 3 session auth
  frontend/    React 19 + TypeScript (Vite) + React Router — Sprint 3 UI:
    auth/      session login/logout, route guards
    pages/     employee list/detail, org structure, data quality, headcount dashboard
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
`manager` (Line Manager), `employee` (Employee, self-scope only).

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
- All API access goes through the shared RBAC permission classes + field-tier
  serializer mixin from `rbac_audit` (Sprint 2). No per-module access control.
- Slow work (imports, report generation, webhooks) runs in Celery, never in-request.
- Sensitive fields (race, gender, disability, pay, ratings, assessment results)
  are tiered per `Data-Dictionary.md` — hard constraint from the sprint plan.

## CI

`.github/workflows/hcm-ci.yml` (repo root): Django checks + missing-migration
guard + tests; frontend typecheck/lint/build. The Sprint 2 RBAC regression
suite becomes the baseline every module sprint extends.
