# ADR-012: Deployment versioning and rollback

**Status:** Proposed

## Context

`hcm-ci.yml` today is test-only (backend/backend-postgres/frontend/e2e) — there is no deploy job,
no image registry, no dependency-update automation, and `docker-compose.yml` builds images from
source (`build: ./backend`, `build: ./frontend`) rather than pulling a versioned, previously-tested
artifact. ADR-005 already decided the hosting shape — Docker Compose, single node, three
environments, explicitly **no Kubernetes/orchestration** at this scale — which rules out the
revision/traffic-split rollback mechanism a project like TTLI_LMS uses on Azure Container Apps.
Single-node Compose has no second warm instance to shift traffic to, so rollback here is
necessarily a redeploy, not a routing change. That's a real, load-bearing difference worth stating
explicitly rather than borrowing language from a different topology.

One existing fact makes this more than an abstract concern: `backend`'s container command is
`python manage.py migrate && gunicorn ...` — **migrations run automatically on every container
start.** That means rolling the app back to an older image after a newer migration has already run
forward does *not* revert the schema; the old code simply keeps running against whatever schema is
currently applied. This makes the expand/contract discipline in §Decision below load-bearing, not
optional — it's the only thing that keeps an old image able to run at all after a rollback.

Follows the shape of `C:\applications\docs\templates\DEPLOYMENT_ROLLBACK_PLAYBOOK_TEMPLATE.md`,
Pattern B (single node / Compose, no orchestrator).

## Decision

- **Versioning:** every backend/frontend image is built once in CI and tagged with the git SHA
  (`ghcr.io/<org>/hcm-backend:<sha>`, same for frontend). GHCR (GitHub Container Registry) is the
  default target — no new cloud subprocessor relationship, and it's free for a repo already on
  GitHub; revisit only if/when ADR-005's "on-prem VM vs. Azure" decision lands on Azure, at which
  point ACR becomes the natural choice instead.
- **Compose stops building in production.** Add `docker-compose.prod.yml` (an override, same
  pattern TTLI already uses for its own prod compose file) that replaces every `build:` line with
  `image: ghcr.io/<org>/hcm-backend:${IMAGE_TAG}` / `hcm-frontend:${IMAGE_TAG}`. `docker-compose.yml`
  itself stays build-from-source, for local dev only.
- **Deploy = `docker compose pull && docker compose up -d` with `IMAGE_TAG` pinned to a specific
  SHA.** Not `latest` — an `IMAGE_TAG` env var set explicitly per deploy, so the deployed version is
  always a deliberate, recorded choice, never whatever happened to be newest at pull time.
- **Rollback = re-pin `IMAGE_TAG` to the previous SHA and `docker compose up -d` again.** Keep the
  last 3 image tags pulled and present in the host's local Docker image cache specifically so a
  rollback doesn't depend on registry reachability under incident pressure. This is **minutes, not
  seconds** — there is no warm second instance to shift traffic to on a single node. State that
  plainly rather than implying an instant rollback this topology can't deliver.
- **Dependency updates:** Dependabot watching `hcm/backend/requirements.lock` and
  `hcm/frontend/package-lock.json`, weekly, grouped, security patches immediate. The resulting PR
  runs the existing `hcm-ci.yml` gate unchanged — no special path.
- **Migrations stay expand/contract**, same rule TTLI documents: add nullable, backfill, constrain
  — never all three in one release. Given migrations run automatically on container start (see
  Context), this is what makes "roll the image back" a safe operation at all. A contract-phase
  migration (dropping/constraining a column) must not ship in the same release a rollback might be
  needed for.
- **Pre-migration backup gate:** run the `docs/RUNBOOK.md` backup command
  (`pg_dump -Fc`) immediately before any deploy whose migration touches an existing column or table
  — independent of, and in addition to, the nightly automated backup. Concrete commands live in
  `docs/RUNBOOK.md`'s new "Deploy & rollback" section rather than duplicated here.
- **Production promotion gate:** a GitHub Environment named `production` with a required reviewer,
  the same mechanism-not-convention approach as TTLI's — until ADR-005's hosting decision (on-prem
  VM vs. Azure) lands, "deploy" is a manual `ssh` + the commands above run by whoever has the
  approval; automating the trigger itself is a follow-up once the target host is fixed.

## Consequences

- No canary/blue-green traffic ramp exists at this topology — a bad deploy is user-visible for the
  time it takes to notice and re-run the rollback command, not auto-healed by a metrics-driven
  ramp. Revisit if ADR-005 is ever revisited toward an orchestrator (its own consequences section
  already says "revisit only if NFRs change materially" — this ADR doesn't reopen that question).
- Introduces a registry (GHCR) as a new moving part; `hcm-ci.yml` needs a new job to build, tag,
  and push on merge to `main` — currently it stops at green tests.
- `docker-compose.prod.yml` needs to exist before this is implementable; today only the
  build-from-source `docker-compose.yml` does.
