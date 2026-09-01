[← Back to the sprint plan index](../Sprint-Plan-HCM-System.md)

# Release-evidence index

**Added:** 2026-08-28, closing HR_Code_report.md's M6 ("create a release-evidence index linking each
control to its dated artifact... keep engineering checks in CI and store organisational sign-offs outside
source control where confidentiality requires it, with only references/status in the repository").

This is the one place that answers "what actually gates a release, and where's the proof it ran" —
without duplicating the mechanism itself, which lives in `.github/workflows/hcm-ci.yml` and
`docs/RUNBOOK.md`. Update this file's **Status**/**Last verified** columns when a control's story changes;
the mechanism columns should rarely need touching.

## Automated, CI-enforced

Evidence for these is the CI run itself (or, until GitHub Actions billing is unblocked — see
`docs/SESSION-STATE.md` — the equivalent commands run locally and referenced in the commit that shipped
the change).

| Control | Mechanism | Status |
|---|---|---|
| Backend tests (SQLite) | `hcm-ci.yml` `backend` job | Enforced every push/PR |
| Backend tests (PostgreSQL, the production engine) | `hcm-ci.yml` `backend-postgres` job | Enforced every push/PR |
| Django system checks | `manage.py check --fail-level WARNING` (`backend` job) | Enforced |
| Migration-drift guard | `manage.py makemigrations --check --dry-run` (`backend` job) | Enforced |
| Celery app loads / beat schedule resolves | `backend` job's dedicated step | Enforced |
| Production secret fail-fast | `backend-production-config` job — proves a weak `SECRET_KEY`/`ASSESSMENT_WEBHOOK_SECRET` under `DEBUG=0` refuses to boot, and that `check --deploy --fail-level WARNING` is otherwise clean with real secrets | Enforced (added 2026-08-28, H2) |
| OpenAPI schema validity + generated-types.ts drift | `contract-drift` job | Enforced (added 2026-08-28, M2) |
| Frontend lint / TypeScript / production build | `frontend` job | Enforced |
| Chunk-size budget (regression ceiling on `index`/`face-api.esm`) | `vite.config.ts`'s `chunkSizeBudget` plugin, runs inside the build itself | Enforced |
| Contract-import guard (no reverting a migrated page to a removed handwritten type) | `npm run lint` → `scripts/check-contract-imports.mjs` | Enforced |
| E2E (Playwright, real browser against seeded Django + Vite) | `hcm-ci.yml` `e2e` job | Enforced |
| Dependency currency | `.github/dependabot.yml` (weekly, grouped minor/patch; security patches immediate) | Enforced (added 2026-08-28) |
| Container base-image provenance | Every base image in `hcm/backend/Dockerfile`, `hcm/frontend/Dockerfile`, `hcm/docker-compose.yml` pinned by digest | Enforced at build time (added 2026-08-28) |
| Celery worker/beat liveness | `docker-compose.yml` healthchecks (`celery inspect ping`; schedule-store freshness) | Verified against a real running stack 2026-08-28, not just YAML |

## Needs a human — not yet performed

These cannot be manufactured by engineering (HR_Code_report.md's own framing). Record the actual
artifact/date here once each happens; until then this table itself **is** the honest status.

| Control | Owner | Status | Evidence location once done |
|---|---|---|---|
| Role-based stakeholder UAT (employee/manager/HR/recruiter/compensation/EE/auditor) | HR/talent/EE/compensation stakeholders | **Not started** | link the sign-off doc here |
| Security review (auth, step-up, downloads, audit, lifecycle cascades) | Security reviewer | **Not started** | — |
| Privacy review (biometrics, disability data, union representation, protected documents) | Privacy/legal reviewer | **Engineering review complete; independent review not started** | `docs/PILOT-PRIVACY-REVIEW.md` |
| Non-biometric identity/check-in alternative + appeal procedure, verified in practice | HR | **Not started** | — |
| Database + media restore rehearsal, into an isolated environment, with hash verification | Ops | **Not started** — `docs/RUNBOOK.md` documents the *procedure*; nobody has run it against this repo's actual data yet | — |
| Load/capacity test at realistic employee/document/history volume | Ops | **Not started** | — |
| Accessibility audit (WCAG 2.2 AA) | Accessibility reviewer | **Not started** | — |
| Formal pilot acceptance or rejection | Product owner | **Not started** | — |

## Deliberately not automatable, and not attempted here

- **Full deploy/rollback pipeline (H3):** ADR-012 (proposed, `adr/ADR-012-deployment-rollback-versioning.md`)
  covers the design; a real GHCR-publish job, a protected GitHub `production` Environment, and an actual
  restore rehearsal are infrastructure/credential decisions outside what a code change alone can prove.
- **Entra/OIDC SSO and SAP payroll integration (H4):** need a real tenant and a real SAP counterpart;
  nothing here should claim these are "done" until tested against the actual systems.

## Related documents

- `docs/RETENTION-MATRIX.md` — per-model/file-field retention status (M7).
- `docs/RUNBOOK.md` — backup/restore/deploy *procedures* (the how); this file is the *status* (the whether-it-happened).
- `docs/SESSION-STATE.md` — narrative history of what shipped, session by session.
