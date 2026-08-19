# Operations Runbook (H3 ops/observability)

Concrete procedures for the things ADR-005 states as policy but doesn't spell
out: backup, restore, and reading whether an instance is actually healthy.
Everything below assumes the `docker-compose.yml` topology in `hcm/` —
service names and volume names come straight from it.

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

## What this runbook deliberately does not cover

Redis (`celery`/cache) is not backed up — it holds only in-flight task state
and throttle counters, nothing that isn't safe to lose and rebuild. Secrets
(`.env`, `POSTGRES_PASSWORD`, `SENTRY_DSN`, etc.) are out of scope here —
they belong in whatever secrets manager the actual hosting environment uses,
never in this repo or in a backup archive alongside the data it protects.
