# Contract End-Date Tracking & Renewal Decisions — Design Spec

**Status:** Approved by user, ready for implementation planning.
**Part of:** C1 (Position/establishment control), part 2 of 3. Part 1 (Position/establishment) shipped 2026-08-20 (`b34bfb7`). Part 3 (onboarding/offboarding checklists + termination cascades) is separate future work.

## 1. Purpose

Fixed-term employees (`EmployeeVersion.employment_status == FIXED_TERM`) have no tracked contract end date anywhere in this system today, and no mechanism reminds anyone their contract is approaching expiry. This spec adds that tracking, a reminder pipeline, and a real recommend→decide workflow for what happens next (renew / convert to permanent / let lapse) — not just a notification, an actual decision-recording-and-executing mechanism.

## 2. Scope

**In scope:** fixed-term contract end-date tracking, reminders, escalation, and the renew/convert/let-lapse decision workflow described below.

**Explicitly out of scope, by the user's own choice during brainstorming:**
- **Probation-period tracking** — a related but distinct concern (deliberately not bundled into this spec), gets its own future brainstorm.
- **Termination checklists/cascades** (deactivating role assignments, liveness enrolment, collab account flags) — this is C1 part 3's territory per the original C1 spec's §4.4. This spec's "let lapse" action triggers the *existing* termination mechanism (already built, pre-dates this spec) and stops there; it does not add any new post-termination cascade behavior.
- **Employee-facing visibility** — unlike performance agreements (which the employee signs), the employee does not see or participate in this workflow. Only the outcome (their employment record changing) is visible to them, through whatever existing means already surfaces that.
- **Changing other employment terms at renewal time** (pay, grade, department) — a renewal extends the contract end date only, via the same carry-forward mechanism promotions already use for every other field. If a renewal should also come with a promotion, pay change, or transfer, those go through the existing dedicated mechanisms for those (comp proposals, promotions) — not reinvented here.

## 3. Data Model

### 3.1 `EmployeeVersion.contract_end_date`

New field: `models.DateField(null=True, blank=True)`. Meaningful only when `employment_status == FIXED_TERM`; ignored otherwise. Nullable by design — existing fixed-term employees don't get a forced backfill migration (see §7).

`VERSION_CARRY_FIELDS` **does** include `contract_end_date`, the same as `position` — an unrelated version change (e.g. a mid-contract promotion via the existing promotion mechanism) must not silently wipe it, since the underlying contract hasn't ended just because the employee changed role. Losing it on an ordinary promotion would incorrectly trip the new "missing contract end date" data-quality check (§7) and silently stop that employee's reminders. `decide_contract_action` (§4)'s `RENEW` and `CONVERT_PERMANENT` paths explicitly set their own value on the version they create (`decided_end_date`, or `None` for a conversion) — an explicit set on creation overrides the carried-forward default, the same relationship `position=` already has with carry-forward elsewhere in `core_hr`.

### 3.2 `ContractRenewalDecision`

One row per upcoming contract expiry. Lives in `core_hr` (see §8 for why no new app).

```python
class ContractRenewalDecision(TimestampedModel):
    class Status(models.TextChoices):
        RECOMMENDED = "recommended", "Recommended"
        DECIDED = "decided", "Decided"

    class Action(models.TextChoices):
        RENEW = "renew", "Renew"
        CONVERT_PERMANENT = "convert_permanent", "Convert to permanent"
        LET_LAPSE = "let_lapse", "Let lapse"

    employee_version = models.OneToOneField(
        "core_hr.EmployeeVersion", on_delete=models.CASCADE,
        related_name="contract_renewal_decision",
    )
    status = models.CharField(max_length=20, choices=Status.choices)

    recommended_action = models.CharField(max_length=20, choices=Action.choices, null=True, blank=True)
    recommended_by = models.ForeignKey("core_hr.Employee", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    recommended_at = models.DateTimeField(null=True, blank=True)
    recommended_comment = models.TextField(blank=True)
    recommended_end_date = models.DateField(null=True, blank=True)  # only meaningful when recommended_action == RENEW

    decided_action = models.CharField(max_length=20, choices=Action.choices, null=True, blank=True)
    decided_by = models.ForeignKey("core_hr.Employee", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_comment = models.TextField(blank=True)
    decided_end_date = models.DateField(null=True, blank=True)  # only meaningful when decided_action == RENEW

    resulting_employee_version = models.ForeignKey(
        "core_hr.EmployeeVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
```

**A row only exists once someone has acted** — no synthetic "pending, nothing happened yet" row. Before any action, there is simply no `ContractRenewalDecision` for that `EmployeeVersion`; the reminder job (§5) works directly off `EmployeeVersion.contract_end_date`, not off this table, for the "who hasn't acted yet" query.

**hr_admin can decide without a prior recommendation** — during escalation (§5), hr_admin may act directly; the row is created straight at `status=DECIDED` with every `recommended_*` field left null. If a manager's recommendation exists first, hr_admin sees it and can accept it as-is or override with a different `decided_*` action/date.

## 4. Decision Flow & State Machine

- **Manager recommends** (`recommend_contract_action(employee_version, *, actor, action, comment="", end_date=None)`): creates the row (if none exists) at `status=RECOMMENDED`. Raises if a row already exists for this version (no re-recommending — matches this codebase's existing "no double-submit" pattern from Position's `submit_for_approval`). `end_date` required when `action=RENEW`, must be after the version's current `contract_end_date`; ignored otherwise.
- **hr_admin decides** (`decide_contract_action(employee_version, *, actor, action, comment="", end_date=None)`): creates the row if none exists, or updates an existing `RECOMMENDED` row. Raises if the row is already `DECIDED` (no re-deciding, same idempotency guard as Position's `decide_step`). Sets `status=DECIDED`, then **executes immediately, in the same transaction** — deciding and executing are one action, not two, matching how Position's `decide_step` both records and advances state in one call:
All three call `Employee.apply_lifecycle_event()` (`core_hr/models.py:231`) directly — the existing close-current/open-next mechanism every version change already goes through, which also carries `VERSION_CARRY_FIELDS` forward and records the linking `EmploymentEvent` automatically. No new version-management logic; this spec only supplies the `event_type` and `field_updates` for each action:
  - `RENEW`: `apply_lifecycle_event(event_type=CONTRACT_RENEWAL, effective_date=<today>, contract_end_date=decided_end_date)`. **`CONTRACT_RENEWAL` is a new `EmploymentEvent.EventType` choice this spec adds** — `employment_status` carries forward unchanged (still `FIXED_TERM`), only `contract_end_date` is overridden. Sets `resulting_employee_version` to the new version (`to_version` on the created `EmploymentEvent`).
  - `CONVERT_PERMANENT`: `apply_lifecycle_event(event_type=CONTRACT_CONVERSION, effective_date=<today>, employment_status=PERMANENT, contract_end_date=None)`. **`CONTRACT_CONVERSION` already exists** as an `EventType` choice (`core_hr/models.py:396`) — added in an earlier sprint but never wired to anything until now. Sets `resulting_employee_version`.
  - `LET_LAPSE`: `apply_lifecycle_event(event_type=TERMINATION, effective_date=<today>, termination_reason=CONTRACT_END)` — `termination_reason=CONTRACT_END` already exists too. Per `apply_lifecycle_event`'s own behavior, `TERMINATION` closes the current version without opening a new one; `resulting_employee_version` stays null.

  `effective_date` for all three defaults to the decision date (`decided_at`'s date) — not the contract's original `contract_end_date` — since `apply_lifecycle_event` requires `effective_date > current.valid_from` and a decision recorded before the actual expiry (the normal case, given reminders start 60 days out) should take effect immediately rather than backdating to a not-yet-arrived date.

Both functions live in `core_hr/services.py` (or a new `core_hr/contracts.py` if `services.py` is getting large — implementer's call, matching this project's existing file-size judgment elsewhere) and, like Position/establishment's service layer, contain **no role/permission checks** — those belong in the view layer, matching the established 403-vs-400 split (wrong role → 403 in the view; wrong state → 400 from the service raising a domain error).

## 5. Reminders & Escalation

Mirrors PC-1's `performance/reminders.py` → `performance/tasks.py` → `CELERY_BEAT_SCHEDULE` shape exactly — same proven pattern, applied to a new date field.

New settings (deployment-configurable, matching `POSITION_APPROVAL_CHAIN`'s precedent):
```python
CONTRACT_REMINDER_OFFSETS_DAYS = [60, 30, 14, 7]   # days before contract_end_date the manager is reminded
CONTRACT_ESCALATION_DAYS = 14                       # days before contract_end_date hr_admin joins in, if unrecommended
```

Daily Celery task (`core_hr/tasks.py`, added to `CELERY_BEAT_SCHEDULE` alongside the existing entries):
1. Query current `EmployeeVersion`s where `employment_status == FIXED_TERM`, `contract_end_date` is set, and `contract_end_date - today` matches one of `CONTRACT_REMINDER_OFFSETS_DAYS`, and no `ContractRenewalDecision` with `status=DECIDED` exists yet.
2. For each: notify the employee's line manager via `notifications.notify()` (matching every other consumer's call shape from H3 slice 1) — **unless** a `ContractRenewalDecision` already exists (manager already recommended; the ball is now in hr_admin's court, so the manager doesn't keep getting pinged for a decision that isn't theirs to make anymore).
3. hr_admin gets notified on the same reminder offsets whenever **either** condition holds: a `ContractRenewalDecision` already exists at `status=RECOMMENDED` (it's hr_admin's turn to decide, regardless of how many days remain), **or** no row exists at all and `contract_end_date - today <= CONTRACT_ESCALATION_DAYS` (the manager hasn't acted and time is short). Once `status=DECIDED`, neither role gets reminded further — the row is closed out.

## 6. Access Control

New `ContractPermission` (shaped like `EstablishmentPermission`):

| Action | Roles |
|---|---|
| Read (own reports) | line manager |
| Read (all) | hr_admin, auditor |
| Recommend | line manager, own direct reports only |
| Decide | hr_admin only |

No `comp_manager`/`accounting_officer` involvement — this is a manager+HR administrative decision, not a budget/establishment-control one (contrast Position/establishment's 3-role chain).

## 7. Existing Data & the Data-Quality Registry

No backfill migration. Existing fixed-term employees with no `contract_end_date` are surfaced by a new check registered in `core_hr/data_quality.py` (already home to core_hr's built-in checks per H3 slice 5's registry) — a new `DataQualityException.ExceptionType.MISSING_CONTRACT_END_DATE` choice, flagging any current `FIXED_TERM` version with `contract_end_date IS NULL`.

The one-time historical data entry to clear those flags happens through Django admin (`EmployeeVersionAdmin`, already exists — confirm `contract_end_date` is editable there, add it if the admin uses an explicit `fields`/`fieldsets` list). This is a one-off cleanup task, not an ongoing workflow, so it doesn't need its own frontend surface — consistent with how this project has handled comparable one-time administrative corrections elsewhere. Going forward, `Employee.objects.hire()` gains an optional `contract_end_date=None` kwarg (same pattern as part 1's `position=None` addition) so new fixed-term hires can have it set at hire time and never need the data-quality flag at all.

## 8. Why `core_hr`, Not a New App

Position/establishment got its own app because *two* other apps (`core_hr` and `recruitment`) both needed a direct relationship into it. Nothing outside `core_hr` needs `ContractRenewalDecision` or `contract_end_date` — this is a natural extension of what `core_hr` already owns (`employment_status`, `termination_reason` already live there). A new app would add a cross-app import boundary with no corresponding decoupling benefit. `contract_reminders`/`contracts.py`'s only outward dependency is `notifications.notify()` — a one-directional import every other consumer (performance, compensation, policies) already makes the same way.

## 9. Frontend

New page, `/contract-renewals`, following `PositionsPage.tsx`'s established three-tier shape (list + summary + per-row actions gated by role and status):
- List of `EmployeeVersion`s with `employment_status=FIXED_TERM` and a set `contract_end_date`, each showing its `ContractRenewalDecision` status if one exists (none / recommended / decided) and the underlying employee/manager.
- Manager's view: a "Recommend" action (choose action + optional new end date + comment) on their own reports' rows, visible only once no decision exists yet.
- hr_admin's view: a "Decide" action on any row not yet `DECIDED`, pre-filled with the manager's recommendation if one exists, editable before submitting.
- Summary stats mirroring `PositionsPage.tsx`'s vacancy-stats block: count expiring within `CONTRACT_REMINDER_OFFSETS_DAYS[0]` days, count awaiting a manager recommendation past the escalation threshold, count decided this month.

## 10. Testing

Standard TDD for this project:
- `core_hr` unit tests for `recommend_contract_action`/`decide_contract_action` (state-machine validity, idempotency guards, each of the three decided-action execution paths, the `VERSION_CARRY_FIELDS` carry-forward on RENEW/CONVERT_PERMANENT).
- API tests for `ContractPermission` (manager can only see/recommend own reports, hr_admin sees/decides all, 403 vs 400 split).
- Reminder-task tests using `@override_settings(CONTRACT_REMINDER_OFFSETS_DAYS=..., CONTRACT_ESCALATION_DAYS=...)`, matching how Position/establishment proved `POSITION_APPROVAL_CHAIN` was genuinely configurable — same discipline applies here.
- Data-quality check test (`MISSING_CONTRACT_END_DATE` fires correctly, clears once set).
- One Playwright e2e test: manager recommends → hr_admin decides (RENEW) → new `EmployeeVersion` visible with the extended date, plus a second short test for the LET_LAPSE path confirming the employee's current version closes.

## 11. Known Boundaries

- A contract can only be renewed, converted, or let lapse once per expiry — there's no "undo" or "revise a decided outcome" action (contrast Position's `revise_and_resubmit`, which exists because a *rejected* Position needs a path back to draft; there's no equivalent rejection state here, since hr_admin's decision is final and immediately executed). If a decision turns out to be wrong, fixing it means directly correcting the resulting `EmployeeVersion` through existing means, same as correcting any other historical HR record today.
- No SLA/overdue alerting beyond the reminder offsets and escalation threshold — if hr_admin also lets an escalated contract run past its end date with no decision, nothing currently auto-terminates or auto-flags it as breached. Worth a future data-quality check (fixed-term, past end date, no `DECIDED` `ContractRenewalDecision`) if this proves to be a real gap in practice — not built speculatively now.
