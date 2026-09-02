# Operational metrics, dashboard and alerts

## What is instrumented

The backend records low-cardinality operational metrics in Django's shared cache (Redis in Compose/deployed
environments). It deliberately records no route, employee, recipient, payload, email address or free text.

- API request counts by HTTP method and status class, plus aggregate duration sum/count.
- Success/failure counts and timestamps for the fixed scheduled-task set and collaboration sync task.
- Notification email attempts, successes, failures and last failure time.
- Collaboration integration attempts, successes, failures, skips and freshness timestamps.

Cache-backed counters can reset when Redis is deliberately flushed or replaced. Prometheus handles counter resets; the
dashboard must not treat a reset as evidence of zero historical failures. Authoritative workflow and audit records stay
in PostgreSQL.

## Secure scrape setup

`GET /metrics` is disabled and returns `404` until `METRICS_BEARER_TOKEN` is set to at least 32 characters. It uses a
dedicated machine credential and constant-time comparison; it is unrelated to employee sessions. Generate and store the
token in the deployment's secrets manager, and restrict the endpoint to the monitoring network at the reverse proxy too.

Example Prometheus configuration (substitute a secrets-injected file; do not commit the token):

```yaml
scrape_configs:
  - job_name: hcm
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /run/secrets/hcm_metrics_token
    static_configs:
      - targets: [hcm-backend.internal:8000]
```

The repository provides `hcm/ops/observability/grafana-dashboard.json` and `prometheus-rules.yml`. Import/provision them
in the selected monitoring platform and route warning/critical severities to named owners. Repository artifacts are not
evidence that a live Prometheus, Grafana or paging integration exists.

## Alert response

- Target down: check backend container health, `/readyz`, proxy/network policy and token-secret consistency.
- API 5xx ratio: correlate application logs/Sentry by time, check database/cache readiness, then identify the failing
  workflow without adding employee identifiers to metric labels.
- Latency: compare request rate, database saturation and worker contention; use tracing/logs for route-level diagnosis.
- Task failed/stale: inspect the named Celery task and worker/beat health, then run only its documented idempotent replay.
- Notification failures: confirm in-app rows still exist, inspect SMTP configuration and retry through an approved
  delivery process.
- Integration stale: check whether the integration is intentionally disabled before paging; if enabled, inspect provider
  availability and reconciliation output before replay.

## Evidence boundary

Automated tests prove counter behavior, privacy-minimal labels, token protection and failure-path instrumentation.
Production completion still requires deployed scrape evidence, imported dashboard screenshots/links, alert delivery to
named owners, and a controlled alert drill. Record those external artifacts in `docs/RELEASE-EVIDENCE.md`.
