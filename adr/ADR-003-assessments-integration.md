# ADR-003: Assessments — integrate third-party provider

**Status:** Accepted (ratified 2026-08-12)

## Context
Psychometric assessment is a specialist domain with professional-standards obligations (HPCSA-registered instruments in SA). Building internally without psychometrician input is explicitly barred by the sprint plan.

## Decision
Integrate a third-party provider behind a provider-agnostic adapter interface (`assign`, `status`, `result`) with signed-webhook result ingestion. Module code never imports a concrete adapter directly.

## Consequences
- Sprint 0 action A4: shortlist 1–2 providers with documented APIs.
- Provider swap = new adapter + configuration, not a rewrite (Sprint 12 acceptance criterion).
- Assessment results are classified **Sensitive** and route through the shared RBAC layer.
