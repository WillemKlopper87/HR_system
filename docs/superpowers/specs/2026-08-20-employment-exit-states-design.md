# Employment Exit States & Access Cascade — Design Spec

**Status:** Approved by user (decisions recorded in §3), ready for implementation.
**Part of:** C1 part 3 (lifecycle). This spec covers the **exit state machine and access cascade**. The
onboarding/offboarding **checklists** are the companion slice and are specified separately.

## 1. The problem

### 1.1 A live access hole

A terminated employee keeps their access today. Traced across three layers:

- `Employee.apply_lifecycle_event(TERMINATION)` (`core_hr/models.py`) closes the current `EmployeeVersion`
  and does nothing else. `is_active` appears nowhere in `core_hr` or `rbac_audit` outside tests, so the
  person's Django login still works.
- Their `RoleAssignment` rows keep `revoked_at = NULL`.
- `active_roles_for()` (`rbac_audit/permissions.py`) filters only on `revoked_at` and `role.active` — it
  never consults employment status.

Net effect: someone terminated yesterday can log in today holding every role they held before. An
`hr_admin` leaver retains org-wide access to every employee record. `login_view` calls `authenticate()`
with no employment check anywhere in the path.

### 1.2 "Terminated" is too blunt a concept

The system models exit as a single instantaneous `EmploymentEvent.TERMINATION`. Real exits are not one
thing, and they do not all have the same access consequence:

| Situation | Employment | Access | Reversible |
|---|---|---|---|
| **Suspended** — pending a hearing | Continues | Locked out | Yes — lifting restores it |
| **Serving notice** — resignation accepted, 30 days | Continues | Retained to the last day | Yes — withdrawals happen |
| **Immediate dismissal** | Ends now | Gone now | No |
| **Normal termination** | Ends on a date | Gone on that date | No |

Collapsing these into one event means either cutting access to someone who is still working their notice,
or leaving it live for someone who was walked out this morning. Both are wrong.

### 1.3 Exits are irreversible and currently unguarded

Nothing today asks "are you sure" before an exit, and nothing records who decided it. For a dismissal —
the action most likely to be contested at the CCMA — the system holds no proposer, no confirmer, and no
reason.

## 2. Structural decisions

### 2.1 Suspension is not a lifecycle event

A suspended employee is **still employed**: their `EmployeeVersion` stays open and their `valid_to` stays
null. Suspension is an **access overlay on active employment**, not a version transition, so it cannot
ride `apply_lifecycle_event` the way termination does. This is the single most important shape in this
spec — modelling suspension as a lifecycle event would corrupt the EEA2 workforce-movement record, which
counts terminations.

### 2.2 An exit is a reviewable object, not a fire-and-forget event

This codebase already runs this pattern twice — `establishment`'s position approval chain and `core_hr`'s
contract recommend→decide handshake both park a proposed change until someone confirms it. Exits get the
same shape: proposed → confirmed → executed, with cancellation available before execution.

That yields the "are you sure" control, makes a mis-captured exit a cancellation rather than an incident,
and produces the audit trail (who proposed, who confirmed, when, why) that a contested dismissal needs.

### 2.3 Execution is scheduled, not immediate

The cascade fires on the **effective date**, and immediately when that date is today or already past. This
is the only rule that is correct for both cases in §1.2: a notice period keeps access to the last day,
while a same-day dismissal loses it at once. Scheduled executions ride the existing daily Celery beat job
that already carries contract reminders (`core_hr/tasks.py`) — no new infrastructure.

## 3. Recorded decisions

Both settled by the user during design:

1. **Confirmation is tiered by severity.** Actions with CCMA exposure or that are hardest to undo require
   a *second person* to confirm; routine leavers do not, so an ordinary resignation isn't bottlenecked on
   a second signature.
2. **Suspension is a full lockout, restorable.** Login disabled, roles revoked, liveness enrolment
   suspended — matching precautionary suspension, where someone is off systems and premises pending a
   hearing. Lifting restores exactly what was revoked.

## 4. Data model

### 4.1 `EmploymentChange` (new, in `core_hr`)

One row per proposed change to an employee's employment state.

- `employee` — FK.
- `change_type` — see §4.2.
- `state` — `PROPOSED` → `CONFIRMED` → `EXECUTED`, plus `CANCELLED`. `CONFIRMED` means "authorised and
  awaiting its effective date"; `EXECUTED` means the cascade has run.
- `effective_date`.
- `reason` — free text, required. A dismissal without a recorded reason is not defensible.
- `proposed_by` / `proposed_at`, `confirmed_by` / `confirmed_at`, `executed_at`, `cancelled_by` /
  `cancelled_at` / `cancellation_reason`.
- `revoked_role_assignments` — the role assignments this change revoked, so a lift restores precisely
  those rather than guessing. See §6.2.
- `resulting_event` — FK to the `EmploymentEvent` created on execution, nullable (suspensions create none).

### 4.2 Change types and their confirmation tier

| Change type | Ends employment | Confirmation | Note |
|---|---|---|---|
| `SUSPENSION` | No | **Second person** | Access overlay only; version stays open |
| `LIFT_SUSPENSION` | No | **Second person** | Restores what the suspension revoked |
| `DISMISSAL_SUMMARY` | Yes, immediately | **Second person** | Effective date is today by definition |
| `DISMISSAL_MISCONDUCT` | Yes | **Second person** | |
| `DISMISSAL_INCAPACITY` | Yes | **Second person** | |
| `OPERATIONAL_REQUIREMENTS` | Yes | **Second person** | Retrenchment — CCMA-exposed |
| `RESIGNATION` | Yes | Proposer confirms | The 30-days-from-acceptance case |
| `RETIREMENT` | Yes | Proposer confirms | |
| `CONTRACT_END` | Yes | Proposer confirms | Already produced by C1 part 2's `let_lapse` |
| `DEATH` | Yes | Proposer confirms | Factual record, not a contested decision |

"Second person" means `confirmed_by` must differ from `proposed_by`. Both must hold `hr_admin`.

The ending types map onto the existing `EmploymentEvent.TerminationReason` values, which already cover
resignation, the three dismissal grounds, operational requirements, retirement, death and contract end —
no new termination vocabulary is introduced.

## 5. State machine

```
              propose
                 │
                 ▼
            [PROPOSED] ──── cancel ────▶ [CANCELLED]
                 │
              confirm  (second person, for the tiered types)
                 │
                 ▼
            [CONFIRMED] ─── cancel ────▶ [CANCELLED]
                 │
        effective_date reached
        (or already today/past)
                 │
                 ▼
            [EXECUTED]          ← terminal; the cascade has run
```

- Cancellation is permitted from `PROPOSED` and `CONFIRMED` — i.e. right up until the cascade runs. This
  is what makes a mis-captured exit recoverable, which is the control the user asked for.
- `EXECUTED` is terminal. Undoing a genuine mistake after execution means re-hiring or lifting a
  suspension through the normal path, not editing history — consistent with how this system treats every
  other executed decision.
- Only one non-terminal `EmploymentChange` may exist per employee at a time, so two people can't
  independently propose conflicting exits.

## 6. The access cascade

### 6.1 On execution of an ending type, or a suspension

Atomically, and each step audit-logged via `rbac_audit`'s existing `log_access`:

1. **Revoke every active `RoleAssignment`**, recording which ones on the `EmploymentChange`.
2. **Disable the Django login** (`Employee.user.is_active = False`), where one exists.
3. **Suspend the liveness/biometric enrolment**, so a departed or suspended person cannot pass a check.
4. For **ending** types only, close the employment via the existing `apply_lifecycle_event(TERMINATION,
   termination_reason=…)`, producing the `EmploymentEvent` that feeds EEA2.

A silent mass-revocation would be worse than the hole it closes; every step is logged.

### 6.2 On execution of `LIFT_SUSPENSION`

Restore precisely what the matching suspension revoked: re-grant those roles, re-enable the login,
restore the enrolment. A restored grant is a **new** `RoleAssignment` referencing the lift — the system
records that access was removed and later returned, rather than pretending the revocation never happened.

### 6.3 The cascade is non-destructive

**Nothing in the cascade deletes a record.** It withdraws *access* and leaves *history* intact. This is
explicit because the two are easy to conflate — "remove their access" and "remove their data" are one
sentence apart in a requirement and worlds apart in an audit.

Concretely, on any exit including a summary dismissal:

- The `EmployeeVersion` is **closed** (`valid_to` set), never deleted. The full version chain — every
  department, grade, manager and pay-relevant attribute the person ever held — survives.
- An `EmploymentEvent` is **created**, carrying the termination reason. This is the EEA2
  workforce-movement record and the dated fact that the exit happened.
- The `EmploymentChange` itself is retained: who proposed it, who confirmed it, when, and the reason —
  the provenance a contested dismissal turns on.
- `RoleAssignment` rows are **revoked** (`revoked_at` set), not deleted, so "what access did this person
  hold on the day in question" remains answerable.
- `LivenessCheck` history is untouched — the record of where and when someone checked in is exactly the
  kind of evidence an attendance or desertion dispute needs.
- Every step writes an `AuditLogEntry`, which is itself under a 60-month **retain** rule.

The one thing that is *deactivated rather than kept usable* is the biometric **descriptor** on
`BiometricEnrollment`. That is a matching key, not evidence — POPIA treats biometrics as special personal
information and there is no audit reason to keep a departed person's face template live. Its history is
preserved by `simple_history`, consistent with that model's own documented approach.

### 6.4 Module boundaries

`core_hr` is in `SHARED_KERNEL` and cannot import domain apps; `identity_verification` is a domain app,
and that rule is mechanically enforced by `rbac_audit/test_module_boundaries.py`.

The cascade therefore uses the **registry pattern already proved out in `core_hr/data_quality.py`**:
handlers register from their own `AppConfig.ready()`, and `core_hr` dispatches without importing a peer.
Handler failure is isolated per the same reasoning — one failing handler must not abort the exit or
prevent the others running — with the failure logged loudly rather than swallowed.

## 7. Record retention & auditability

A dismissal can be referred to the CCMA, and an audit can ask about an exit long after it happened. The
records above must therefore outlive the employment by a wide margin. South African practice under the
BCEA is that employment records are kept for **three years after termination**; a disputed dismissal can
easily still be live within that window, and an EEA/AA audit reaches back over reporting years.

**Current posture — verified against the seeded rules, not assumed.** `RetentionRule`'s seeded defaults
are `rbac_audit.AuditLogEntry` (60 months, *retain*), `rbac_audit.StepUpGrant` (1 month, delete — ephemeral
auth grants), and `recruitment.Applicant` (12 months, anonymise — unsuccessful candidates, who are not
employees). **No rule touches `core_hr.Employee`, `EmployeeVersion`, `EmploymentEvent`, or
`RoleAssignment`.** Employment history is not currently at risk from the retention executor.

**The risk this spec closes by naming it.** That safety is incidental, not designed: the retention
executor is generic and honours whatever rules exist, so someone could later add a
`core_hr.Employee` rule with `delete` or `anonymise` and quietly destroy the evidence trail for a live
labour case. Two requirements follow:

1. Seed explicit `RETAIN` rules for `core_hr.EmploymentEvent` and `core_hr.EmploymentChange` so the
   intent is recorded in data rather than resting on the absence of a rule. A future reader adding
   retention policy then has to consciously override a stated decision instead of filling a silent gap.
2. Any retention rule proposed against an employment entity is a decision with legal exposure and
   belongs in an ADR, not a migration. Note it in `Data-Dictionary.md` alongside the tables.

**Out of scope here:** a legal-hold mechanism (freezing a specific employee's records while a case is
open, overriding any retention rule) is the right long-term answer and is not built. It belongs with C5
labour relations, where the case itself would be modelled — the hold should hang off the case, not off a
manually-set flag someone has to remember to clear.

## 8. Access control

| Action | Who |
|---|---|
| Propose any change | `hr_admin` |
| Confirm (tiered types) | A *different* `hr_admin` |
| Confirm (routine types) | The proposer, or any `hr_admin` |
| Cancel | Any `hr_admin` |
| Read | `hr_admin`, `auditor` |

Line managers do not propose exits in this design. Suspensions and dismissals originate from a
disciplinary process (C5 labour relations, not yet built); resignations are captured by HR on receipt.

## 9. Testing

- The security property, end-to-end: an employee who held a role and is then exited genuinely fails
  `active_roles_for()` and can no longer reach a role-gated endpoint. This is the test that catches a
  regression of §1.1.
- **The history property, end-to-end** (§6.3): after a *summary dismissal* — the most abrupt path, and the
  one most likely to be litigated — assert that the person's full `EmployeeVersion` chain is still
  present and readable, that an `EmploymentEvent` exists carrying the termination reason, that the
  `EmploymentChange` still names its proposer, confirmer and reason, that revoked `RoleAssignment` rows
  still exist with `revoked_at` set rather than having been deleted, and that `LivenessCheck` history
  survives. This is the test that catches someone later "tidying up" the cascade into a delete.
- Suspension → lift restores exactly the roles that were revoked, and no others.
- A suspension leaves `valid_to` null and creates **no** `EmploymentEvent` (§2.1) — the EEA2 guard.
- Tiered confirmation: same-person confirm is rejected for a dismissal, accepted for a resignation.
- Cancellation from both `PROPOSED` and `CONFIRMED` leaves access untouched.
- A future-dated change does **not** cascade until its date; a today-or-past one cascades on confirmation.
- A failing handler doesn't abort the exit or block sibling handlers.
- An employee with no `user` account doesn't break the cascade.

## 10. Known boundaries

- **No automatic reversal after execution.** Undo is re-hire or lift, not history editing (§5).
- **Suspension has no maximum duration and no automatic review prompt.** A precautionary suspension that
  is forgotten stays in force. A data-quality check (suspended beyond N days, no lift proposed) is the
  natural net and is deliberately deferred — it belongs with the same sweep that would catch a lapsed
  contract with no decision.
- **Notice-period access is all-or-nothing.** Someone serving notice keeps full access to their last day.
  Graduated withdrawal (e.g. losing write access while keeping self-service) is not modelled.
- **No integration with the collab platform's account state.** `Employee.collab_user_id` exists and the
  integration is outbound-only by design; pushing a deactivation is a C3/integration concern, not this
  spec's.
