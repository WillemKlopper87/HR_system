# Sentech HCM — frontend

React 19 + TypeScript + Vite + React Router. The full application README (layout, demo logins, module rules) is
one level up in [`hcm/README.md`](../README.md); planning docs are in the repo root.

## Run

```powershell
npm install
npm run dev        # http://localhost:5173 — proxies /api and /admin to the Django dev server on :8000
npm run lint       # oxlint
npm run build      # tsc -b && vite build  → dist/
```

The backend must be running (`python manage.py runserver` in `../backend`) — see the app README for seeding demo
data and the login list.

## Layout

```
src/
  api/          fetch client (CSRF-aware, global 401 → login), hand-written API types, reference-data context
  auth/         AuthContext (session + sessionExpired), RequireAuth/RequireRole route guards,
                RequirePayrollStepUp (TOTP enrolment + challenge wrapper), LoginPage
  pages/        one file per route; sub-components for a page live in that file
  components/   pieces shared across pages
  ee-reporting/ constants mirror of backend ee_reporting/constants.py + MatrixTable
  liveness/     face-api.js wrapper + camera capture (lazy-loaded route)
  index.css     the whole stylesheet (CSS variables in :root)
public/models/  face-api model weights (committed, ~7 MB)
```

## Conventions

- Role-gated pages go under `<RequireRole roles=[…]>` in `App.tsx`; every-employee self-service pages
  (`/my-*`) are routed under `RequireAuth` only and scoped server-side.
- The API client throws `ApiError(status, body)`; a 401 anywhere (except login/me) clears the session and
  redirects to `/login` with a "session expired" notice and a return-to path.
- No tests yet — the Playwright suite is H2 on the roadmap (`ROADMAP-2026-08.md`).

## Docker

`Dockerfile` builds the SPA and serves it with nginx (`nginx.conf`), proxying `/api`, `/admin`, `/healthz` and
`/static` to the `backend` service; wired up in `../docker-compose.yml` as `frontend` on port 8080.
