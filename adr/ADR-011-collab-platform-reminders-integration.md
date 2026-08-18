# ADR-011: HR system → collab platform integration for scheduled reminders and tasks

**Status:** Proposed (2026-08-18) — companion to ADR-010; collab-side prerequisites tracked in that repo's brief

## Context
Staff forget KPI deadlines until the last minute; the HCM has no notification channel; the internal collaboration
platform (`internal-collaboration-platform`, FastAPI/React) already has per-user work items (`/work-items/my`),
critical announcements with a blocking popup and ack-rate reporting, a per-user realtime notification topic and
calendars — the surface staff actually look at daily.

## Decision
- The HCM is the system of record; integration is **outbound-only, best-effort, idempotent**: a Celery-beat job
  computes who is outstanding per phase and, through `integrations/collab.py`, upserts one collab work item per
  employee per stage (`external_ref = hcm:agreement:{id}:{stage}`, priority rising toward the deadline, closed by
  the HCM when signed), a Head digest item, and department-scoped critical announcements at phase open/overdue.
- No ratings, scores, evidence or signatures leave the HCM; collab items carry title, due date and a deep link.
  A "done" in collab never counts as signed.
- Identity mapping by work email now (`Employee.collab_user_id` cached), by shared IdP subject once both systems
  sit behind one IdP (ADR-004 / Keycloak decision).
- Collab platform must add: service-account/API-key auth, `WorkItem.external_ref`+`source`, lookup by
  external_ref, (optional) status webhook. Feature flag `COLLAB_ENABLED` on the HCM side.

## Consequences
- The same reminder engine later feeds email/in-app notifications (H3) — one scheduler, many channels.
- Cross-repo work item X0 must land before PC-1's reminders are visible; PC-1 itself ships regardless.
- If collab is down, contracting still opens; reminders retry with backoff and are logged in `ReminderLog`.
