[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

### X0 — Collab platform integration surface (other repo: `internal-collaboration-platform`)
**Status: done** (2026-08-18, collab repo commit `23d4f05`) — API-key auth → service user, `WorkItem.source/external_ref` (alembic 0010), `/integrations` router (upsert/read by external ref, ensure project, create+publish announcement with `dedupe_key`), `create_service_account` script, 8 tests, CI LiveKit env fix. Outbound webhook (item 4) left optional — the HCM polls by external_ref.
- [x] Service-account / API-key auth for machine callers
- [x] `WorkItem.external_ref` + `source` (unique per source), `GET /work-items?external_ref=`, upsert semantics
- [x] Announcements creatable/publishable by the service account; identity lookup by work email
- [ ] (optional) outbound webhook on work-item status change · [x] fix that repo's CI so this ships green

