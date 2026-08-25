# Onboarding / Offboarding Checklists — Design Spec

**Status:** Decided shape carried forward from `docs/SESSION-STATE.md` (2026-08-21); this spec fills in the
detail and is ready for implementation without further sign-off.
**Part of:** C1 part 3 (lifecycle), slice 3 — the companion to
`docs/superpowers/specs/2026-08-20-employment-exit-states-design.md`, which explicitly deferred this piece:
"The onboarding/offboarding checklists are the companion slice and are specified separately." That spec's exit
state machine and access cascade are **not** touched here beyond one registry hook (§6).

## 1. The problem

### 1.1 Two of the five demoable-lifecycle breaks

`docs/MVP-Backlog.md` Part B walks one employee from arrival to departure and finds five breaks. Two of them
are this slice's job:

> **Onboard** (tasks, IT, first week) — ❌ Missing
> **Offboard** (exit cascade) — ❌ Missing … *carries the integrity payload the Gap Survey flagged*

The offboarding half of that second line is partly done: `EmploymentChange` execution (slice 1/2, already
shipped) revokes roles, disables login and suspends biometric enrolment the moment an ending-type change
executes. What is still missing on both sides is the **task layer**: the checklist of concrete, ownable
actions a real HR/IT/line-manager process runs around a hire or an exit — laptop issued, access card cut,
induction booked; laptop returned, exit interview held, final pay confirmed. None of that is access control.
All of it is currently tracked nowhere in the system (a spreadsheet, an inbox, someone's memory) and so it
never demos and is never auditable.

### 1.2 Why not just hard-code the task list

`docs/SESSION-STATE.md` already decided this: *"versioned templates mirroring `AgreementTemplate`, so HR can
change the process after the demo without a deploy."* A hard-coded Python list of onboarding steps is exactly
the shape that broke `ee_reporting`'s occupational levels and `establishment`'s approval chain before those
were pulled into data — HR's real process changes (a new IT ticketing tool, a revised induction day) more
often than this codebase ships, and nobody should need a migration to add "collect banking details" to the
new-hire list.

## 2. Structural decisions

### 2.1 One app, one model pair, a `direction` field — not two apps or two model families

Onboarding and offboarding are the same *shape* of object (a versioned template of ordered, owned tasks; an
instance per employee per trigger; each task completed/not, by whom, when) with a different *population* of
tasks and a different trigger. Splitting them into two apps or two parallel model families would duplicate
every piece of machinery below (the template CRUD, the instance-from-template copy, the completion service,
the permission class, the two frontend pages) for zero behavioural difference. A single `direction` field
(`onboarding` / `offboarding`) on both `ChecklistTemplate` and `ChecklistInstance` carries the distinction
everywhere it matters — which template a hire vs. an exit pulls from, which list a page shows — at the cost
of one extra column. This mirrors `EmploymentChange.ChangeType` carrying "ends employment or not" as data
rather than as two separate models.

### 2.2 A new app, `onboarding` — not folded into `core_hr`

`core_hr` is `SHARED_KERNEL` (`hcm/README.md`'s module rules) and may not import any domain app; every other
domain app may import `core_hr` freely. A checklist is lifecycle-**adjacent** — it hangs off `hire()` and off
`EmploymentChange` execution — but it is not core identity/version data the way `Employee`/`EmployeeVersion`
are, and nothing outside this feature needs to read a checklist the way, say, `ee_reporting` needs to read
`EmployeeVersion.race`. Per this repo's "one Django app per module" convention (`NEXT_AGENT_BRIEF.md` §8),
that makes a new app the right shape, not an addition to the shared kernel. Consequence: `core_hr` cannot call
into this app directly (§6 below covers how the hire/exit triggers reach it anyway), but this app freely
imports `core_hr.models.Employee` and `core_hr.models.EmploymentChange`, exactly as `performance` and
`compensation` already do.

Named `onboarding` rather than something direction-neutral like `checklists`: the brief's own suggested name,
and consistent with this codebase's preference for a concrete noun over an abstract one (`establishment`,
`compensation`, `policies` — not `records` or `items`). The docstring on `onboarding/apps.py` says explicitly
that the app covers both directions, so the name doesn't mislead a future reader long.

### 2.3 Deliberately simpler than `AgreementTemplate` — no sections, no signing, no scoring

`AgreementTemplate`/`TemplateSection`/`TemplateElement`/`PerformanceAgreement` is the versioned-template
pattern to mirror **structurally** (a versioned template → an instance snapshotted from it → per-item state),
not **completely**. A KPI scorecard needs weighted sections, five-level rating descriptors, two-party
signatures against a hashed PDF. A checklist item needs a label, a description, an owner-role hint, and an
order — it gets ticked off, not scored or signed. Copying the signing/scoring machinery here would be
building for a use case this feature doesn't have. So:

- No `TemplateSection` equivalent — checklist items are a single flat ordered list per template. Real
  onboarding/offboarding checklists (the brief's own examples: IT access, asset issue/return, exit interview)
  don't naturally group into weighted sections the way a scorecard's objectives do; if that changes, a
  `category` free-text field on the item is a one-migration addition, not a redesign.
- No signatures, no PDF snapshot, no rating scale. "Complete" is a boolean transition (`completed_at` set or
  not), by one actor, with an optional note — the ECT Act signing apparatus that `AgreementSignature` exists
  for has no equivalent requirement here (nobody disputes at the CCMA whether a laptop was returned the way
  they dispute a performance rating).
- Versioning is still real: `ChecklistTemplate.version`, auto-incremented per `name`+`direction` (§4.1), so
  editing the onboarding process after go-live means publishing a new version, never mutating a version that
  active instances were snapshotted from (§2.4).

### 2.4 Instances snapshot their items from the template — templates are otherwise immutable once published

`ChecklistInstanceItem` copies `label`/`description`/`owner_role` from `ChecklistTemplateItem` at instance
creation, exactly as `AgreementElement` copies from `TemplateElement`. This is the same reasoning as that
model's own docstring: once an instance exists, a later edit to the *template* (HR renames a task, drops one,
re-orders the list for the next hire) must not silently rewrite a checklist someone is partway through
completing, or retroactively change what "task 3" meant for an audit looking back at who did what. A
template's items are therefore only editable while its `status` is `DRAFT`; once `PUBLISHED`, changing the
process means creating the next `version` (§4.1's auto-increment), the same discipline
`AgreementTemplate`'s `new-version` action already established in this codebase.

### 2.5 Triggers are automatic by default, with an `hr_admin` manual fallback

The brief's decided shape is automatic: an onboarding instance on `hire()`, an offboarding instance when an
ending-type `EmploymentChange` executes. Two situations that automatic path alone doesn't cover, both real
enough to need a documented answer rather than silently doing nothing:

- **No template is published yet** for that direction (e.g. this feature ships before anyone has authored an
  onboarding template) — the hook is a no-op (§6.2), not an error; a hire or an exit must never fail because
  a checklist template doesn't exist.
- **A template is published later**, after some employees already have no checklist, or HR wants to
  re-issue one for an employee whose situation changed. `hr_admin` can create an instance directly
  (`POST /checklist-instances/`, §5), gated to one active instance per employee per direction at a time
  (mirroring `exits.py`'s `_assert_no_open_change` — see §4.2), so a manual create can't collide with the
  automatic path either.

## 3. Recorded decisions

Settled here, in the same "state the decision and the reasoning" style as the sibling spec:

1. **Who can complete a task: `hr_admin` always; the employee's line manager only for tasks explicitly owned
   by `line_manager`, only for their own reporting chain; never the employee themselves.** The brief floats
   line-manager involvement for onboarding specifically ("maybe the employee's line manager for some
   onboarding tasks"); the natural boundary is the task's own `owner_role` hint, which already exists to
   describe who does the work — using it to gate *who may tick it off* costs nothing extra and matches intent
   exactly (a task hinted "IT" isn't something a line manager should be marking done). Self-completion is
   deliberately excluded: several realistic tasks (exit interview held, asset returned and inspected, NDA
   witnessed) are attestations *about* the employee, not *by* them, and self-ticking a compliance record the
   employee has an interest in undermines exactly the kind of audit trail this system exists to keep. An
   employee can **see** their own checklist (next decision) but never mark a row done.
2. **Who can see a checklist: `hr_admin` and `auditor` see everything; a `line_manager` sees checklists for
   employees in their reporting chain (RBAC-Roles.md's `own_team` row scope, via the existing
   `rbac_audit.permissions.is_in_reporting_chain`); an employee sees their own.** Templates themselves (the
   process definition, not any one person's instance) are visible to `hr_admin`/`auditor` only — the same
   read/write split as `EmploymentChangePermission`, since template content isn't something a line manager or
   employee has a standing reason to browse, only their own instance.
3. **Manual instance creation is `hr_admin`-only**, not exposed to line managers — creating the record that
   starts a process is an HR act in this codebase's existing pattern (proposing an `EmploymentChange`,
   proposing a `Position`), completing individual tasks within it is where other roles participate.

## 4. Data model

All models live in `onboarding/models.py`, subclass `core_hr.base.TimestampedModel` (`created_at`/`updated_at`
only — no `simple_history`; the completion trail itself, plus the audit log every service function writes to,
is this data's history, the same choice `AgreementTemplate`'s template layer makes).

### 4.1 `ChecklistTemplate`

| Field | Type | Notes |
|---|---|---|
| `name` | varchar(200) | e.g. "Standard onboarding" |
| `direction` | enum | `onboarding` / `offboarding` |
| `version` | smallint, default 1 | Auto-assigned server-side: `(max version for this name+direction) + 1`. Never client-writable |
| `status` | enum | `draft` → `published` → `retired` |
| `created_by` | FK employee, null | `SET_NULL` |
| `published_at` | datetime, null | |

`UniqueConstraint(name, direction, version)` — extends `AgreementTemplate`'s `unique_template_name_version`
with `direction`, since that model has no direction-like field but this one does: two different directions
legitimately share a `name`+`version` (both seeded as "Standard onboarding"/"Standard offboarding" v1, say),
because `version` is auto-assigned per `name`+`direction`, not per `name` alone.
`ChecklistTemplate.current_for(direction)` — the latest `published` row for that direction, highest `version`
first; this is what §6's automatic triggers resolve against, and what a manual create defaults to when no
explicit template is given.

### 4.2 `ChecklistTemplateItem`

| Field | Type | Notes |
|---|---|---|
| `template` | FK ChecklistTemplate | `CASCADE`, `related_name="items"` |
| `label` | varchar(300) | e.g. "Issue laptop and access card" |
| `description` | text, blank | Free detail |
| `owner_role` | enum | `hr` / `it` / `line_manager` / `employee` / `other` — who normally does this; also the completion gate for `line_manager` (§3.1) |
| `order` | smallint, default 0 | |

Editable only while `template.status == draft` (enforced in the service layer, not a DB constraint — same
split `exits.py`'s module docstring argues for: a state-machine rule belongs in the service, not the model).

### 4.3 `ChecklistInstance`

| Field | Type | Notes |
|---|---|---|
| `employee` | FK Employee | `CASCADE` |
| `template` | FK ChecklistTemplate | `PROTECT` — the exact template version this instance was drawn from |
| `template_version` | smallint | Snapshot of `template.version` at creation, for a readable label even if the FK is later inspected out of context |
| `direction` | enum | Snapshot of `template.direction` |
| `status` | enum | `active` → `completed`, or `cancelled` |
| `triggering_change` | FK core_hr.EmploymentChange, null | `SET_NULL`; set only for an offboarding instance created by the automatic exit hook (§6.2) — null for onboarding instances and for any manually-created instance |
| `created_by` | FK Employee, null | `SET_NULL`; null = created by the automatic hire/exit hook, set = the `hr_admin` who manually triggered it (§2.5) |
| `completed_at` | datetime, null | Set when every item on the instance is complete |

`UniqueConstraint(employee, direction, condition=Q(status="active"), name="one_active_checklist_per_employee_per_direction")`
— the DB-level backstop (Django 5.2 conditional unique constraint), same shape as `EmploymentChange`'s own
`one_open_employment_change_per_employee`, with a service-layer pre-check (`ChecklistError`, not a raw
`IntegrityError`) ahead of it for a clean error message, mirroring `exits.py::_assert_no_open_change`.

### 4.4 `ChecklistInstanceItem`

| Field | Type | Notes |
|---|---|---|
| `instance` | FK ChecklistInstance | `CASCADE`, `related_name="items"` |
| `label` / `description` / `owner_role` / `order` | — | Copied from the template item at creation (§2.4); independently editable never — this row's identity *is* the snapshot |
| `completed_by` | FK Employee, null | `SET_NULL` |
| `completed_at` | datetime, null | Null = not done |
| `notes` | text, blank | Optional context on completion (e.g. "returned laptop has a cracked screen, logged with IT") |

`is_complete` is `completed_at is not None`, not a separate boolean — one fewer place for the two to drift.

## 5. Service layer (`onboarding/services.py`)

Every function is `@transaction.atomic`, matching `exits.py`'s convention, and every state-changing one writes
an `AuditLogEntry` via `rbac_audit.audit.log_access` at `FieldTier.INTERNAL` (this data carries no PII beyond
who-did-what, the same tier `exits.py` uses for its own cascade log lines). `ChecklistError(ValueError)` is
the one exception type, exactly mirroring `EmploymentChangeError`.

- `create_template(*, name, direction, actor, items=None) -> ChecklistTemplate` — auto-assigns `version`
  (§4.1); optionally seeds items in the same call.
- `publish_template(template, *, actor) -> ChecklistTemplate` — `draft → published`; refuses an empty
  template (a published checklist with zero tasks is a mistake, not a valid state) and refuses a template not
  in `draft`.
- `retire_template(template, *, actor) -> ChecklistTemplate` — `published → retired`; a retired template is
  simply excluded from `current_for()`, so new instances stop drawing from it while existing instances (which
  hold their own item snapshot) are entirely unaffected.
- `create_checklist_instance(employee, template, *, actor=None, triggering_change=None) -> ChecklistInstance`
  — the one instantiation path every trigger below funnels through: copies every template item into a fresh
  `ChecklistInstanceItem`. Raises `ChecklistError` if the employee already has an active instance for that
  direction.
- `create_onboarding_checklist_on_hire(employee) -> int` — resolves `ChecklistTemplate.current_for(onboarding)`;
  0 if none published, else creates the instance and returns 1. This is the function registered as a hire
  hook (§6.1) — its `int` return matches the hook-handler contract §6 defines, for the same audit-worth
  reasoning `access_cascade.py`'s handlers use.
- `create_offboarding_checklist_on_exit(employee, change) -> int` — same shape for `offboarding`, records
  `triggering_change=change`. Registered as the exit-completion hook (§6.2).
- `complete_item(item, *, actor, notes="") -> ChecklistInstanceItem` — sets `completed_by`/`completed_at`/
  `notes`; if every sibling item on the instance is now complete, marks the instance `completed` with
  `completed_at`. Raises `ChecklistError` if the item is already complete (no silent re-completion overwriting
  who/when).
- `reopen_item(item, *, actor) -> ChecklistInstanceItem` — clears `completed_by`/`completed_at`/`notes`; if the
  instance had been marked `completed`, reverts it to `active`. The undo path for a mis-click — deliberately
  symmetrical with `cancel_employment_change` existing as the undo for a mis-proposed exit.

Role/permission checks are **not** here, matching `exits.py`'s own split (module docstring, §8 of the sibling
spec): who *may* call `complete_item` for a given item is a view-layer 403 decision (§7), because — like the
tiered-confirmation rule there — it needs to inspect an actor/target relationship
(`is_in_reporting_chain`) the service layer has no business owning.

## 6. Hooking into `hire()` and the exit cascade

`core_hr` cannot import `onboarding` (§2.2). Both triggers therefore go through a new registry module,
**`core_hr/lifecycle_hooks.py`**, built to the same shape as `core_hr/access_cascade.py` and
`core_hr/data_quality.py`: a domain app registers a handler from its own `AppConfig.ready()`; `core_hr`
dispatches by name without ever importing the app; a failing handler is caught, logged loudly, and never
blocks the hire or the exit it's hanging off. Handler contract:

```python
def hire_handler(employee) -> int: ...
def exit_completion_handler(employee, change) -> int: ...
```

### 6.1 Hire hook

`EmployeeManager.hire()` (`core_hr/models.py`) gains one line at the end of its existing `@transaction.atomic`
block: `lifecycle_hooks.run_hire_handlers(employee)`. This is the one change to `hire()` itself the brief's
context section flags as a hang-point; nothing else about `hire()` changes.

### 6.2 Exit hook

`exits.py::execute_employment_change`'s existing ending-type branch (the one that already calls
`employee.apply_lifecycle_event(...)` — §6.1 of the sibling spec) gains one line immediately after that call
succeeds: `lifecycle_hooks.run_exit_completion_handlers(employee, change)`. This is additive only — it does
not touch the access-cascade steps (`_withdraw_access`), the tiered-confirmation rule, or any other part of
the state machine, per the guardrail that slice's core logic is done and tested. It deliberately fires only
for `ENDING_CHANGE_TYPES`, not for `SUSPENSION` — a suspended employee is still employed (sibling spec §2.1)
and has not "left" in any sense a checklist should react to. Because `record_executed_exit` (the contract-lapse
fast path) calls `execute_employment_change` internally, a lapsed fixed-term contract gets an offboarding
checklist through the exact same code path as every other exit, with no special-casing.

### 6.3 Registration

`onboarding/apps.py`'s `ready()`:

```python
from core_hr import lifecycle_hooks
from . import services
lifecycle_hooks.register_hire_handler("onboarding.ChecklistInstance", services.create_onboarding_checklist_on_hire)
lifecycle_hooks.register_exit_completion_handler("onboarding.ChecklistInstance", services.create_offboarding_checklist_on_exit)
```

## 7. Access control

Two permission classes in `onboarding/permissions.py`, both following `EmploymentChangePermission`'s coarse
gate + service/view narrowing shape:

| Action | Who |
|---|---|
| Read a template (`GET /checklist-templates/`, items) | `hr_admin`, `auditor` |
| Create/publish/retire a template, edit its items | `hr_admin` only |
| List/read checklist instances | `hr_admin`, `auditor` — all; `line_manager` — their reporting chain (`is_in_reporting_chain`); any employee — their own only |
| Manually create an instance (`POST /checklist-instances/`) | `hr_admin` only |
| Complete/reopen an item | `hr_admin` — any; `line_manager` — only items with `owner_role=line_manager`, only for their reporting chain; nobody else |

`ChecklistInstanceViewSet.get_queryset` implements the row-scoping directly (mirroring how
`EmployeeVersion`'s nested `contract_renewal_decision` read gate is a row-relational check in the serializer
layer, not a blanket permission class) — `hr_admin`/`auditor` see everything; otherwise the query is narrowed
in Python to rows where `employee_id == actor.id` or (`line_manager` and `is_in_reporting_chain(actor,
row.employee)`). `ChecklistInstanceItemViewSet.complete`/`reopen` re-derive the same chain check plus the
`owner_role` gate per item, since — as in `exits.py`'s tiered-confirm rule — that decision needs the specific
row's data, not just the actor's role.

## 8. Testing

Mirroring `core_hr/test_exits.py`'s "spec's list is a floor, not a ceiling":

- Publishing an empty template is rejected; publishing a non-`draft` template is rejected.
- Template versioning: creating a second template with the same `name`+`direction` auto-assigns the next
  version; publishing v2 does not retire v1 automatically (retiring is a deliberate separate action, so an
  in-flight rollout can run both briefly if HR chooses).
- `hire()` creates an onboarding instance with the current published template's items copied in, when one
  exists; creates none when no onboarding template is published (no exception raised — the hire still
  succeeds).
- `hire()` with **no** onboarding template published, followed by one being published later, then a manual
  `hr_admin` create — the backfill path.
- An ending-type `EmploymentChange` executing creates an offboarding instance with `triggering_change` set;
  a `SUSPENSION` executing does **not**.
- Only one **active** instance per employee per direction — both the service-layer pre-check and, in a
  dedicated test, the DB constraint itself (bypassing the service to prove the backstop is real).
- Completing every item on an instance marks it `completed` with a `completed_at`; reopening one item on a
  `completed` instance reverts it to `active`.
- Completing an already-complete item raises `ChecklistError`.
- Role gating at the API level: `line_manager` can complete a `line_manager`-owned item for their own report,
  cannot for someone outside their chain, and cannot complete an `it`-owned item even for their own report;
  a plain `employee` can read their own checklist but gets 403 attempting to complete anything; `auditor` can
  read everything but gets 403 on every write action.
- A failing hook handler (simulated via `temporary_hire_handler`/`temporary_exit_completion_handler`, mirroring
  `access_cascade.py`'s `temporary_exit_handler`) does not block `hire()` or exit execution.

## 9. Known boundaries

- **No reminders/escalation for an overdue task.** Every other scheduled-nudge feature in this codebase
  (`core_hr/tasks.py`'s contract reminders, `performance`'s `ReminderLog`) took its own design pass; bolting a
  reminder schedule onto checklist items here would be scope creep on a slice that's already large. A stale
  checklist is visible on the page (no completion date, still `active`) but nothing pushes a notification
  about it yet.
- **No IT/asset-management integration.** An "issue laptop" task is a checkbox HR or IT ticks by hand; there
  is no asset-tag model or serial-number tracking behind it. Out of scope the same way A3 #14 (time-clock
  hardware) is — this system tracks the *fact* of the task, not the underlying inventory system.
- **A retired template's existing instances are unaffected, but there is no UI to browse retired templates'
  history separately from published ones** beyond the plain list filter — acceptable for a first slice; a
  dedicated "template history" view is a natural follow-up once there's more than one or two versions to look
  back over.
- **Line-manager completion rights are all-or-nothing per `owner_role=line_manager` item**, not further
  scoped by task content — matches the coarseness `EmploymentChangePermission` already accepts for its own
  role gate.
