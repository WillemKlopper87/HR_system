# Sentech HCM — Application

Modular-monolith HCM system. Planning and architecture docs live one level up in `HR_system/`:
`Sprint-Plan-HCM-System.md` (backlog) · `Architecture-Design.md` (ADRs, module rules) · `Data-Dictionary.md` · `RBAC-Roles.md` · `Sprint-0-Decision-Log.md`.

## Layout

```
hcm/
  backend/     Django 6.1 + DRF (ADR-001) — one Django app per domain module
    config/    settings, urls, wsgi/asgi
    core_hr/   employees, org structure, lifecycle (Sprint 1)
    rbac_audit/ shared RBAC + audit + consent layer (Sprint 2)
  frontend/    React 19 + TypeScript (Vite)
  docker-compose.yml  db + redis + backend + celery worker (ADR-005)
```

## Local development

Backend (SQLite fallback — no services needed):

```powershell
cd backend
python -m venv .venv            # NOTE: prefer a venv OUTSIDE OneDrive (see below)
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py runserver   # http://localhost:8000/healthz
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

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
