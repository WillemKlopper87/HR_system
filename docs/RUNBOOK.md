# Operations Runbook (H3 ops/observability)

Concrete procedures for the things ADR-005 and ADR-012 state as policy but
don't spell out: backup, restore, deploy/rollback, and reading whether an
instance is actually healthy. Everything below assumes the `docker-compose.yml`
topology in `hcm/` — service names and volume names come straight from it.

## Health vs. readiness

Two endpoints, deliberately different:

- **`GET /healthz`** — process is up. No dependency checks. What a load
  balancer polls every few seconds; it must never flap because Postgres had
  one slow query.
- **`GET /readyz`** — can this instance actually serve traffic: database and
  cache both reachable. Returns `200 {"status": "ready", "checks": {...}}` or
  `503 {"status": "not_ready", "checks": {...}}` with each check's individual
  result, so a caller sees the whole picture in one request. Point container
  orchestration's *readiness* probe here, `/healthz` at *liveness*.

## Logging

Plain stdlib logging to stderr (`config/settings.py::LOGGING`) — every
gunicorn/Celery deployment already captures that, no new log-shipping
infrastructure required. Level is `DJANGO_LOG_LEVEL` (default `INFO`);
`django.request` always logs 5xx tracebacks at `ERROR` regardless of the root
level, so quieting a noisy module during an investigation can't accidentally
hide a real failure.

## Error tracking (Sentry)

Optional and inert by default. Set `SENTRY_DSN` to enable it (`SENTRY_ENVIRONMENT`
and `SENTRY_TRACES_SAMPLE_RATE` are optional too — see `config/settings.py`).
`send_default_pii` is hardcoded `False`: employee data never goes to a
third-party service by default, POPIA. Leaving `SENTRY_DSN` unset (the
default in dev/CI/any environment without a Sentry project yet) is a no-op —
`sentry-sdk` isn't imported at module load, only inside the `if SENTRY_DSN:`
guard, so a venv that hasn't installed it still boots cleanly.

## Backup

Nightly, automated, off-host — this is the ADR-005 policy; below is how to
actually run it.

**Database** (the record of truth — periods, agreements, evidence metadata,
signatures, audit log):

```bash
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-hcm}" -Fc "${POSTGRES_DB:-hcm}" > hcm-$(date +%Y%m%d).dump
```

`-Fc` (custom format) is required for the parallel/selective restore options
below. Copy the resulting `.dump` file off-host immediately — a nightly cron
entry that also runs the copy step is the actual DR requirement, not just
the dump.

**Media** (uploaded policy documents, agreement PDFs — `policies.Policy.source_file`,
`performance.AgreementDocument.pdf`, `performance.EvidenceItem.file`):

```bash
docker run --rm -v hcm_media:/media -v "$(pwd)":/backup alpine \
  tar czf /backup/hcm-media-$(date +%Y%m%d).tar.gz -C /media .
```

(Volume name is `<project>_media` — Compose prefixes the `media:` volume
declared in `docker-compose.yml` with the project/directory name; confirm
with `docker volume ls` if it doesn't match.)

## Restore

**Database**, into a fresh/empty `db` service:

```bash
docker compose exec -T db pg_restore -U "${POSTGRES_USER:-hcm}" -d "${POSTGRES_DB:-hcm}" --clean --if-exists < hcm-YYYYMMDD.dump
```

**Media**:

```bash
docker run --rm -v hcm_media:/media -v "$(pwd)":/backup alpine \
  sh -c "rm -rf /media/* && tar xzf /backup/hcm-media-YYYYMMDD.tar.gz -C /media"
```

After both restores, run `docker compose exec backend python manage.py migrate`
(picks up any pending migration the dump predates) and check `/readyz`.

## Restore rehearsal

ADR-005 calls for a quarterly rehearsal — restore into a throwaway
environment (not staging/prod) and verify:

1. `docker compose up -d db redis` against fresh volumes, then run both
   restore steps above.
2. `docker compose up -d backend` and confirm `/readyz` reports `ready`.
3. Log in as a seeded demo user (or a real one if this is a genuine prod
   restore rehearsal) and confirm a recently-signed performance agreement's
   PDF still downloads and its sha256 still matches the one recorded on its
   `AgreementSignature` — this is the actual test that both the database
   *and* the media volume restored consistently with each other, not just
   that either one individually "looks fine".

## Deploy & rollback (ADR-012)

Single-node Compose has no second warm instance to route traffic to — deploy and rollback here are
both **redeploys**, on the order of minutes, not the instant traffic-shift a revision-based platform
gets. Say so out loud to whoever's running the rollback under pressure; don't let them expect an
instant fix.

**Deploy** (production host, `hcm/` directory, `docker-compose.prod.yml` per ADR-012):

```bash
export IMAGE_TAG=<git-sha-of-the-build-that-passed-CI>
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

`backend`'s container command runs `python manage.py migrate` automatically on start — this is why
ADR-012 requires every migration to be expand/contract (backward-compatible with the *previous*
release). There is no separate "run migrations" step to remember, and no way to opt out of it per
deploy.

**Before any deploy whose migration touches an existing column or table**, take a fresh backup —
don't rely solely on the nightly cron for this one:

```bash
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-hcm}" -Fc "${POSTGRES_DB:-hcm}" > hcm-pre-deploy-$(date +%Y%m%d%H%M).dump
```

**Rollback** — re-pin `IMAGE_TAG` to the previous known-good SHA and redeploy:

```bash
export IMAGE_TAG=<previous-git-sha>
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Keep the last 3 `IMAGE_TAG` values' images present in the host's local Docker cache
(`docker image ls | grep hcm-`) specifically so this doesn't depend on registry reachability during
an incident. If the migration that shipped with the bad release was expand/contract-compliant (it
must be, per ADR-012), the old code keeps working against the current schema with no schema-side
rollback needed — that compliance is what makes this rollback safe, not optional cleanup.

If the bad release's data corruption goes deeper than "roll the code back" fixes — not just a bad
migration, but bad writes from the bad release — that's the Restore procedure above, not this one:
this section undoes a code deploy, Restore undoes data damage.

## What this runbook deliberately does not cover

Redis (`celery`/cache) is not backed up — it holds only in-flight task state
and throttle counters, nothing that isn't safe to lose and rebuild. Secrets
(`.env`, `POSTGRES_PASSWORD`, `SENTRY_DSN`, etc.) are out of scope here —
they belong in whatever secrets manager the actual hosting environment uses,
never in this repo or in a backup archive alongside the data it protects.
