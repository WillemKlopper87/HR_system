[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

## Sprint 2 — RBAC & Audit Foundation
**Goal:** Shared access-control and audit layer every later module will reuse.
**Status: done** (2026-08-12) — see `hcm/backend/rbac_audit/`. Scheduled retention-rule execution (the `RetentionRule` model exists; the Celery job that acts on it doesn't yet) and the real Employee list/detail UI are explicitly deferred to their own sprints (post-Sprint-16 hardening, and Sprint 3, respectively) — not omissions.

**Tasks:**
- [x] Implement role-based access control at the API layer (not just UI) — `rbac_audit/permissions.py` (`active_roles_for`, `can_access_tier`, `has_row_access`) + `rbac_audit/drf.py` (`RowScopePermission`, `TieredModelSerializer`, `row_scoped_queryset`), proven end-to-end via `core_hr`'s `EmployeeVersionViewSet`
- [x] Define per-field sensitivity rules (demographics/pay visible only to specific roles; aggregated-only for line managers) — `rbac_audit/tiers.py::FIELD_TIERS` (the declarative P/I/S/R map from `Data-Dictionary.md`) + the 8-role grant matrix from `RBAC-Roles.md` seeded via migration `0002_seed_roles`; line_manager's `own_team` scope has no individual Sensitive-tier read (full aggregate dashboards are Sprint 3)
- [x] Implement audit logging: who accessed/edited which sensitive field, when — `rbac_audit/models.py::AuditLogEntry` (append-only — `save()`/`delete()` raise after creation) + `rbac_audit/audit.py::log_access()`; fires on every S/R-tier field read (`TieredModelSerializer`) and every row-scope denial (`RowScopePermission`)
- [x] Build consent-tracking mechanism for demographic self-ID — `rbac_audit/models.py::ConsentRecord` (POPIA lawful-basis register) + `rbac_audit/consent.py` (`record_consent`, `withdraw_consent`, `has_active_consent`); Sprint 15's ESS UI will be its primary caller
- [x] Write RBAC/audit test suite (regression baseline for every future module) — `rbac_audit/tests.py`, 22 tests

**Acceptance criteria:**
- [x] Unauthorized role attempting to access individual-level sensitive data is blocked and logged. — `EmployeeVersionApiTests.test_line_manager_blocked_from_outsider_and_denial_is_logged`, `test_employee_self_scope_blocked_from_colleague` (403 + `AuditLogEntry.Action.ACCESS_DENIED`)
- [x] Every sensitive-field read/write produces an audit record. — `EmployeeVersionApiTests.test_hr_admin_sees_sensitive_fields_and_access_is_logged`; consent grant/withdrawal audited in `ConsentTests`

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, `migrate`, and `manage.py test` all pass — 30/30 tests project-wide (8 core_hr + 22 rbac_audit). CI runs the same suite on every push.

