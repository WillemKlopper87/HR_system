# ADR-005: Hosting — Docker Compose, single node, three environments

**Status:** Proposed (needs Sentech IT decision: on-prem VM vs. Azure)

## Context
Workload is headcount-scale (~600 employees, ≤300 peak concurrent users). NFR targets in `Architecture-Design.md` §9.

## Decision
Docker Compose per environment (dev/staging/prod): `nginx → gunicorn/Django → PostgreSQL`, plus Celery worker + beat and Redis. Object storage as mounted volume (Azure Blob if cloud-hosted). Nightly `pg_dump` + off-host copy; quarterly restore rehearsal is the DR plan — concrete commands and the rehearsal checklist are in `docs/RUNBOOK.md` (H3).

## Consequences
- No Kubernetes/orchestration overhead at this scale; revisit only if NFRs change materially.
- IT must provision the VM(s) or Azure subscription before staging exists (Sprint 0 exit item).
