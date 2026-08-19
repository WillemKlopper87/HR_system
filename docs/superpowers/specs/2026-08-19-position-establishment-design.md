# Design Spec — Position / Establishment Management (C1, part 1 of 3)

**Date:** 2026-08-19 · **Status:** draft for user review · **Source material:** `ROADMAP-2026-08.md` (C1),
`NEXT_AGENT_BRIEF.md` §7.2 #10, "Gap Survey" research artifact (2026-08-19), user Q&A this session.

## 1. Goal

Give Sentech (an SOE, PFMA establishment control) a real notion of an approved post, independent of who currently
holds it: approved-vs-filled visibility, post-numbering, and vacancy rate — none of which exist today. Requisitions
today are free-standing (department + level + grade + headcount, no link to a specific post); this spec ties them to
a specific, individually-numbered, approved-and-vacant `Position`.

C1 was scoped as three separable pieces (user's explicit choice: split into three specs). This spec covers **only**
piece 1, Position/establishment. The other two — `contract_end_date`/`probation_end_date` + reminders, and
onboarding/offboarding checklists with termination cascades (role assignments, liveness enrolment, collab account
flag) — are each their own future brainstorm.

**Non-goals (v1):** editing/re-grading an already-`approved` Position (restructuring a post is abolish-and-recreate,
not an in-place edit); an `abolished` status for permanently retiring a post; a runtime-editable approval-chain
builder (the chain is a deployment-time setting, not a self-service admin screen — user's explicit choice); any of
piece 2/3's scope (contract dates, onboarding/offboarding, termination cascades); the internal-first/external
job-board recruitment posting idea raised mid-session (parked separately, see
`project_hr_system_recruitment_posting_idea` memory — a different subsystem entirely).

## 2. Domain — new app `establishment/`

Joins `SHARED_KERNEL` in `rbac_audit/test_module_boundaries.py` (same reasoning as `notifications` in H3): both
`core_hr` (`EmployeeVersion.position`) and `recruitment` (`Requisition.position`) need a direct FK into it, not a
`queries.py` read seam — a seam only works for read-only derived data, not a real foreign key.

### 2.1 `Position(TimestampedModel)`
- `post_number` (`CharField`, unique, auto-assigned sequentially at creation — `P-00001`, `P-00002`, …)
- `title` (`CharField`, mirrors `EmployeeVersion.job_title` / `Requisition.title`)
- `department`, `occupational_level`, `location` (FK → `core_hr`, `PROTECT`, required)
- `job_grade` (FK → `core_hr.JobGrade`, `PROTECT`, nullable — matches `Requisition.job_grade`'s existing nullability)
- `status`: `draft` / `in_review` / `approved` / `rejected` (`TextChoices`)
- `current_step` (`PositiveSmallIntegerField`, default 0) — index into the configured approval chain; meaningful only
  while `status == in_review`
- `proposed_by` (FK → `Employee`, `SET_NULL`)
- `history = HistoricalRecords()`

Occupancy is **derived, not stored** — a Position is "filled" if any current `EmployeeVersion` (`.as_at(today)`)
points at it; "vacant" means `approved` **and** no current occupant. This matches how `Employee.current_version` is
already derived elsewhere rather than duplicated as a stored flag that can drift.

### 2.2 `PositionApprovalStep(TimestampedModel)`
Append-only audit trail, one row per decision: `position` (FK, `related_name="approval_steps"`), `step_index`,
`role` (`CharField` — a **snapshot** of which role this step required, read from settings at decision time, not a
live reference — so a later chain-length/role change never rewrites history), `actor` (FK → `Employee`,
`SET_NULL`), `decision` (`approved`/`rejected`), `comment` (blank-ok). `created_at` (from `TimestampedModel`) is the
decision timestamp.

### 2.3 Configurable chain
`settings.POSITION_APPROVAL_CHAIN = ["comp_manager", "accounting_officer"]` (default, overridable per deployment —
this is the mechanism that satisfies "the approval chain might change": editing this list and redeploying changes
who approves and how many steps, with zero code changes to the state machine). `hr_admin` always proposes and
submits; the setting only governs what happens after submission.

### 2.4 `establishment/services.py`
- `propose_position(*, title, department, occupational_level, job_grade, location, actor) -> Position` — creates in
  `draft`, assigns the next `post_number`.
- `submit_for_approval(position, *, actor)` — hr_admin only; `draft → in_review`, `current_step = 0`. Raises if not
  currently `draft`.
- `decide_step(position, *, actor, decision, comment="") -> Position` — checks
  `has_role(actor, settings.POSITION_APPROVAL_CHAIN[position.current_step])`; records a `PositionApprovalStep`. On
  `approved`: if this was the chain's last step, `status → approved`; otherwise `current_step += 1`. On `rejected`:
  `status → rejected` immediately, chain stops. Raises `ApprovalError` (same exception shape as `ee_reporting`) on
  wrong role, wrong status, or an already-resolved position.
- `revise_and_resubmit(position, *, actor, **changed_fields)` — hr_admin only, only from `rejected`; may update
  `title`/`department`/`occupational_level`/`job_grade`/`location` (the fields a reviewer could plausibly have
  rejected it over), then `status → draft`, `current_step = 0`. `post_number`, `status`, and `current_step` are
  state-machine-managed, never accepted as input here. The `post_number` and all prior `PositionApprovalStep` rows
  are kept — this is a new cycle on the same post identity, not a new Position.

## 3. Backfill (data migration, `establishment/migrations/0002_backfill_existing_employees.py`)

Creates exactly **one `approved` Position per currently-employed `EmployeeVersion`** (151 in the demo dataset,
1:1 — not grouped/shared even where department+grade+title match exactly, since a Position is one seat). Each
backfilled Position copies that employee's current department/occupational_level/job_grade/job_title/location, and
`EmployeeVersion.position` is linked back to it. No `PositionApprovalStep` rows are fabricated — this is
already-real employment, not a new proposal going through review; the migration sets `status=approved` directly.

Historical `Requisition` rows are also backfilled where possible: a `CLOSED`/`FILLED` requisition whose
`resulting_employee` now has a backfilled Position gets `requisition.position` set to it. `OPEN`/`DRAFT`/`ON_HOLD`
requisitions with no resulting hire predate establishment control and stay unlinked.

## 4. Integration

### 4.1 `EmployeeVersion` (core_hr)
Gains `position` — a **string FK reference** (`models.ForeignKey("establishment.Position", null=True, blank=True,
on_delete=models.SET_NULL)`), not a direct model import. `establishment/models.py` imports `core_hr.models` for its
own FKs (§2.1); a direct import the other way would be circular. String references are standard, idiomatic Django
for this exact situation and are resolved lazily via the app registry — this also means `core_hr` needs no new
production import of `establishment` at all, only `recruitment` does (§4.2).

### 4.2 `Requisition` (recruitment)
Gains `position` (FK → `establishment.Position`, nullable at the DB level for the historical rows in §3, but
enforced as **required** by serializer/service validation on any *newly created* requisition). Creating or updating
a requisition to reference a Position validates `position.status == "approved"` and the Position is currently
vacant (no current occupant) — otherwise a 400 with a clear message. This is the one place `recruitment` gets a real
production import of `establishment` (list/validate positions), which is why `establishment` must be in
`SHARED_KERNEL`.

### 4.3 Hire flow
`recruitment/services.py::_complete_hire` already builds its `Employee.objects.hire(...)` call from
`requisition.department/occupational_level/job_grade/location` — it gains `position=requisition.position`.
`Employee.objects.hire()` gains a matching optional `position=None` kwarg, set onto the new `EmployeeVersion`.
Backward-compatible: every existing caller (bulk import, seed data, tests) keeps working unchanged since the
parameter defaults to `None`. The instant that `EmployeeVersion` exists, the Position reads as filled — no separate
"mark filled" step, since occupancy is derived (§2.1).

### 4.4 Termination
No new Position-side code needed: the moment a termination closes the current `EmployeeVersion` (`valid_to` set),
the Position has no current occupant and reads as vacant again automatically. The actual cascade (deactivating role
assignments, liveness enrolment, collab account flag) is out of scope — that is piece 3 of C1, a separate future
brainstorm per the user's own decomposition choice.

## 5. Access

Reuses the `rbac_audit` role system with a dedicated permission class (`EstablishmentPermission`, shaped like
`EEReportingPermission`): **read** — hr_admin, comp_manager, accounting_officer, auditor, recruiter (recruiter needs
to see approved+vacant positions to build a requisition, but not the approval-chain detail of in-review ones — scope
recruiter's list view to `status=approved` only). **write** — `propose`/`submit`/`revise_and_resubmit` are hr_admin
only; `decide_step` is gated per-step to `has_role(actor, settings.POSITION_APPROVAL_CHAIN[position.current_step])`,
enforced in the view the same way `ee_reporting.views` checks `ee_manager`/`accounting_officer` per action today.

## 6. Frontend

New page `/positions` (`PositionsPage.tsx`), same shape as `EEReportsPage.tsx`: a list (post number, title,
department, status, current incumbent or "Vacant"), a summary stat row (approved / filled / vacant / vacancy rate
%), a "Propose position" form (hr_admin), and per-row Approve/Reject buttons that render only for whoever's role
matches `POSITION_APPROVAL_CHAIN[position.current_step]` — so the UI adapts automatically if a deployment's chain
setting changes, no frontend code change needed for a different chain shape. `RequisitionForm`'s create flow gains a
position picker scoped to `status=approved` and currently vacant.

Nav entry in `navConfig.ts`: visible to hr_admin/comp_manager/accounting_officer/auditor (read)/recruiter
(read, approved-only), matching §5.

## 7. Testing

- **`establishment`**: chain mechanics — happy path through a 2-step default chain; wrong-role rejection at each
  step; wrong-status transitions raise `ApprovalError`; a rejection stops the chain and `revise_and_resubmit` starts
  a fresh cycle on the same `post_number`, preserving prior `PositionApprovalStep` rows; `post_number` uniqueness
  and monotonic assignment. A **settings-override test** (`@override_settings(POSITION_APPROVAL_CHAIN=[...])`)
  proving a *different* chain — different length, different roles — is honored by `decide_step` with zero code
  changes; this is the test that actually proves "configurable" holds, not just the default shape.
- **`recruitment`**: creating a requisition without an approved+vacant position is rejected; against an
  already-filled or non-approved position is rejected; the position-picker endpoint returns approved+vacant only.
- **`core_hr`**: completing a hire against a requisition with a linked position sets `EmployeeVersion.position`; the
  position no longer appears in the vacant list afterward.
- **Backfill**: a migration-correctness test — exactly one `approved` Position per currently-employed
  `EmployeeVersion`, no duplicates, all `post_number`s unique; historical closed requisitions with a resulting hire
  get linked, open ones don't.
- **`rbac_audit/test_module_boundaries.py`**: `establishment` added to `DOMAIN_APPS` and `SHARED_KERNEL` — existing
  test suite confirms the wiring, no new test needed.
- **Browser-verified**: hr_admin proposes a position → submits → comp_manager approves their step (own login) →
  accounting_officer approves the final step (own login) → position shows approved + vacant → a recruiter sees it
  in the requisition's position picker.

## 8. Rollout

Ship as one slice: migrations (schema + backfill data migration) → `establishment` app + services + views →
`recruitment`/`core_hr` integration → frontend. The backfill migration must run before the `Requisition.position`
validation becomes enforced in application code, so existing environments never hit a chicken-and-egg state where
no approved positions exist yet for a brand-new requisition to reference. `manage.py check` and
`makemigrations --check --dry-run` clean, full backend + e2e suites green, same verification bar as every other H-
and C-series slice this project has shipped.
