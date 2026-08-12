# ADR-002: History/versioning — effective-dated rows + change history

**Status:** Proposed (default-accept unless objection before Sprint 1 build starts)

## Context
EE reporting requires "as-at" queries (what was true on date X). Audit requires "who changed what, when." These are different problems often conflated.

## Decision
- **Effective-dated rows** (`valid_from`/`valid_to`) for org-truth entities: employee attributes (`employee_version`), pay bands, org assignments.
- **`django-simple-history`** on all models for change tracking (actor, timestamp, diff).
- **Frozen snapshots** for generated EE reports: an EEA2/EEA4 draft materialises an immutable snapshot; sign-off attaches to the snapshot so later data fixes never alter a signed report.

## Consequences
- Queries for "current" state filter `valid_to IS NULL` (or use a `current` DB view — provided in core_hr).
- Slightly more complex writes (close old row, open new) — encapsulated in model manager methods, never done ad hoc.
