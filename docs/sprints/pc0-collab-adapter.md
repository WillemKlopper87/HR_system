[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

### PC-0 — HR → collab adapter (ADR-011)

**Status: done** (2026-08-18) — see `hcm/backend/integrations/` (new app: `collab.py` client, `sync.py`, `tasks.py`, `management/commands/sync_collab_ids.py`, `test_collab.py`), `core_hr` migration `0004_collab_ids` (`Employee.collab_user_id`, `Department.collab_department_id`), `COLLAB_*`/`HCM_PUBLIC_URL` settings. The other half of the contract is the collab repo's X0 (`app/integrations/router.py`, commit `23d4f05` there).

**Implementation notes:**
- `integrations.collab.CollabClient` (httpx, sync) — `lookup_user_id(email)`, `list_departments()`, `ensure_project()`, `upsert_work_item(external_ref, …)` / `close_work_item()` / `get_work_item()`, `publish_announcement(dedupe_key=…)`. Every call retries connection errors/5xx/429 with exponential backoff (3 attempts) then raises `CollabError(status, body)`; 4xx other than 429 fail fast (a 401 means the key is wrong — retrying would only hide it). `get_client()` returns **None** when `COLLAB_ENABLED` is off or URL/key are missing, so every caller has one honest branch: "collab off → log and continue". Outbound only by design (ADR-011): nothing read from collab drives HCM state.
- Identity mapping: employees by **work email**, departments by **name** (case-insensitive) — `manage.py sync_collab_ids [--dry-run] [--all]` and the `integrations.tasks.sync_collab_ids_task` Celery task write `Employee.collab_user_id` / `Department.collab_department_id`; unmatched rows stay blank and are listed, never guessed. A shared IdP subject (C3) is the better key later.
- New `integrations` app is a plain Django app (imports `core_hr` only — added to the module-boundary test's app list); `httpx` added to `requirements.txt` + lock.
- **Contract tests both sides:** `integrations/test_collab.py` plays the collab platform with `httpx.MockTransport` (keyed upserts, dedupe'd announcements, users by email, department list, injected 5xx/401/connection failures) — 13 tests: idempotent upsert/close/get, announcement dedupe, retry-with-backoff (sleeps asserted `[0.01, 0.02]`), exhausted retries → `CollabError` with status, 401 fails fast without retry, disabled/unconfigured → `get_client() is None`, sync maps/reports/dry-runs/only-missing. The collab repo's `app/tests/test_integrations.py` (8 tests) is the mirror.
- **Proven live, not just mocked:** started the real collab API container, created its service account (`create_service_account`), seeded it, then from the HCM: `sync_collab_ids --dry-run` (Finance matched by name; the two demo datasets share no emails, as expected) and a `CollabClient` round-trip — ensure project in Finance → lookup `thandi@example.com` → upsert `hcm:smoke:1:contracting` (todo/high) → re-upsert (same id, urgent) → close (done) → publish critical department announcement twice (`created` True then False, same id).

**Architecture / design tension:** the adapter is deliberately *dumb* — no HCM domain knowledge (no "agreement", no "phase"); PC-1's reminder job composes titles, refs (`hcm:agreement:{id}:{stage}`) and deep links (`HCM_PUBLIC_URL`) and decides what to send. That keeps the collab dependency at one file and lets a future email/Teams channel sit beside it behind the same job.

**Verification:** `manage.py check`, `makemigrations --check`, `manage.py test` — **448/448** (435 prior + 13). Live cross-repo smoke as above. Frontend untouched.
- [x] `integrations/collab.py` (work items create/close, announcements, retry/backoff), `COLLAB_ENABLED` flag
- [x] `Employee.collab_user_id` + lookup-by-email management command; contract tests against recorded responses
- [x] Celery task wrapper (`sync_collab_ids_task`) · [x] `ReminderLog` model — built in PC-1 (`performance/models/agreements.py::ReminderLog`), which is where the reminder job actually lives

