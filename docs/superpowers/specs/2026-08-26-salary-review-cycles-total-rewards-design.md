# Salary-Review/Bonus Cycles + Total-Rewards Statement — Design Spec

C6 (`ROADMAP-2026-08.md` §7.3 #22, `NEXT_AGENT_BRIEF.md` #22: *"proposals are one-off; no cycle object to batch
increases against a budget, and ESS shows benefits but not a consolidated rewards view."*) Fifth C6 sub-item
shipped, after mandatory-training compliance, succession/talent pools, recruitment interviews/careers-portal, and
performance calibration/360 (all 2026-08-25/26).

---

## 1. The problem

Two independent, only loosely-related gaps share one sprint task:

1. **No batching mechanism for an annual review round.** `compensation.CompProposal` is a one-off row — HR can
   propose one person's new salary, but there's no object representing "FY2026's annual review, running against
   a R2m budget" that a batch of proposals gets raised, tracked, and closed against. Nothing today stops a
   comp_manager from committing far more in increases than the year's payroll budget allows, because nothing
   tracks a budget at all.
2. **No consolidated view of what an employee is actually worth to the organisation.** ESS (`MyBenefitsPage.tsx`,
   Sprint 15) shows elected benefits; nothing shows current salary, where it sits in the person's own pay band, or
   a single "total rewards" picture combining pay + benefits the way real total-rewards statements do.

Gap 2 is the harder one, because this module's entire design philosophy to date has been **"no carve-out,
comp_manager/hr_admin only, module-wide, catalog included"** (`compensation/models.py`'s own docstrings) — a
total-rewards statement is fundamentally self-facing, which is a new shape of exception this module has never
made before. §3 below is the load-bearing decision.

---

## 2. Structural decisions

### 2.1 `CompCycle` extends the existing `compensation` app; `CompProposal` gains an optional `cycle` FK + `proposal_type` rather than forking

Per the task's own steer: build a genuinely new state object (a cycle has its own lifecycle and its own budget
invariant to protect — this is not the "single-row write, validated in the serializer" shape succession's
`CriticalPost`/`SuccessionCandidate` used, §2.4 of that spec), but extend `CompProposal` rather than duplicate its
whole propose→approve→reject workflow, segregation-of-duties check, and pay-band-override machinery a second time
for "cycle proposals." A salary increase raised inside a cycle and a one-off increase raised outside one are the
same kind of decision (a person's pay is changing, someone proposed it, someone else must approve it) — the cycle
is context on top of that decision, not a different kind of decision. `cycle` is nullable: every proposal made
before this slice, and every future ad-hoc proposal outside a formal round, keeps working exactly as it does
today with `cycle=None` and no budget arithmetic in play at all.

### 2.2 Budget shape: a total currency pool, not a % of payroll

Considered a **% of aggregate current payroll** (e.g. "this cycle may spend up to 6% of total remuneration in
scope") and rejected: it requires summing `RemunerationRecord.fixed_remuneration` across every employee in scope
*at the moment the cycle opens*, freezing that sum as a baseline (otherwise "6% of payroll" drifts as new
`RemunerationRecord` rows land mid-cycle from ongoing SAP imports, an outcome nobody actually wants — the budget
should be a fixed envelope, not a moving target). Freezing a baseline is a real, defensible design, but it adds a
genuine new mechanism (a snapshot step, and a decision about what happens if scope changes mid-cycle) for a
benefit this task doesn't need yet: nothing in the brief or `NEXT_AGENT_BRIEF.md`'s gap description asks for
payroll-relative budgeting specifically, only "batch increases against a budget." A flat `budget_amount`
(`DecimalField`) is the simplest shape that satisfies that literally, needs no baseline-freezing step, and is what
`PerformancePeriod` and `CriticalPost`-style objects already default to (plain fields, no derived/frozen
aggregates) when a richer shape isn't asked for. If percentage-of-payroll budgeting is wanted later, it's an
additive field (`budget_pct` + a stored `payroll_baseline_at_open`), not a rename.

### 2.3 Scope: nullable `department` FK, org-wide when null — matches the brief's own wording, not `PerformancePeriod`'s

Checked `PerformancePeriod` (time-window only, no population scope at all — every employee gets an agreement in
whichever period is active) and `learning.CourseRequirement` (`Department` + `OccupationalLevel`, both optional)
as the two existing "cycle-shaped object" precedents. Neither is followed exactly. `PerformancePeriod` doesn't
scope a population because a performance agreement is inherently per-person already (the period is purely a time
window everyone shares) — a comp cycle is the same shape (a time window), but the brief explicitly asks for
department-level scoping ("scope: org-wide or by department"), a real HR need (a supplementary adjustment round
for one division shouldn't need to bound its budget against every other division's payroll too). `department`
alone (not `+OccupationalLevel`) is enough: `CourseRequirement`'s second axis exists because a training
requirement can legitimately target "everyone at a level, in any department" (e.g. "all Senior Management,
org-wide"); nothing about a comp cycle needs that cross-cut — a department-scoped budget is a department-scoped
budget, full stop, and org-wide is simply `department=None`.

Enforcement: `propose_compensation_change` rejects a proposal whose employee's current `department` doesn't match
a department-scoped cycle's `department` (a clean `ValidationError`, not a downstream `IntegrityError` — same
"reject a nonsensical target at the boundary" shape as `CriticalPostSerializer.validate()`'s APPROVED-status
check and `CourseRequirementSerializer.validate()`'s mandatory-course check).

### 2.4 `proposal_type`: `increase` / `bonus`, with type-appropriate (now-nullable) amount fields

`CompProposal.proposed_annual_salary` becomes `null=True, blank=True` (was required) — a bonus proposal has no
"new annual salary" to propose, it has a lump-sum amount. New `bonus_amount` (`DecimalField`, nullable) holds
that. A `CheckConstraint` (`comp_proposal_amount_matches_type`) requires exactly the type-appropriate field to be
set: `increase` ⇒ `proposed_annual_salary` set, `bonus_amount` null; `bonus` ⇒ the reverse. Same "DB constraint as
the defensive backstop, service-layer `ValueError` as the actual 400-producing check" pairing `PayBand`'s
min≤mid≤max constraint already uses — `propose_compensation_change` validates before `.create()` is ever called,
so the constraint should never actually fire in normal use.

`evaluate_requires_override` (pay-band check) only makes sense for `increase` — a lump-sum bonus isn't being
compared against an annual pay band. It's skipped entirely for `bonus` proposals (`requires_override` stays
`False`), which is correct: a bonus can still be flagged for the *other* reason a proposal needs an override
reason at approval — exceeding the cycle's budget (§2.5).

### 2.5 Budget tracking and the over-budget rule: reuses `requires_override`/`override_reason`, doesn't invent a second gate

The brief's own steer ("check `requires_override`/`override_reason` — this precedent for 'flagged but not
blocked, with a recorded reason' is probably the right model to reuse") is followed literally. New
`CompProposal.exceeds_cycle_budget` (`BooleanField`) is the budget-side twin of `requires_override`; `approve_proposal`'s
existing gate —

```python
if proposal.requires_override and not override_reason:
    raise ApprovalError(...)
```

— becomes `if (proposal.requires_override or proposal.exceeds_cycle_budget) and not override_reason`. One
`override_reason` field now covers "why did this get approved despite being outside the pay band and/or over the
cycle's budget" — a proposal that's both simply needs one reason covering both, not two parallel reason fields for
what is, from the approver's chair, a single "I approved this despite a flag, here's why" decision.

**Two different staleness postures, deliberately**: `requires_override` (pay-band) is computed once, at proposal
time, and never recomputed — the thing it's compared against (a pay band for an already-snapshotted job grade)
barely changes in practice. `exceeds_cycle_budget` is different in kind: cycle utilization is a *shared, moving
total* across every proposal in the cycle, changing every time a sibling proposal is created, approved, or
rejected. So it's computed **twice**: once at creation (informational — "as of right now, this would already push
the cycle over"), and recomputed **fresh, under lock** at approval time, because by the time someone gets around
to approving it, other proposals against the same cycle may have moved. Trusting a creation-time snapshot at
approval time would be checking the wrong moment in a genuinely concurrent, multi-actor process.

**The race this closes** (the guardrail's explicit ask): two comp_managers, or one comp_manager double-clicking,
both create/approve proposals against the same cycle at once. Each independently reads "current committed +
pending total," decides they're under budget, and writes — both succeed, and the cycle silently blows its budget
by both amounts combined. Fixed the same way `core_hr.Employee.apply_lifecycle_event` already fixes the
analogous "read current EmployeeVersion, close it, open a new one" race: `select_for_update()` on the row whose
invariant is being protected (there, the `EmployeeVersion`; here, the `CompCycle`), inside `transaction.atomic()`,
around the read-then-decide-then-write critical section. Both the create path (`propose_compensation_change`) and
the approve path (`approve_proposal`) lock the cycle row before computing utilization, so a second concurrent
writer against the *same* cycle blocks until the first transaction commits (or rolls back) rather than reading a
stale total. Utilization itself is **not** a stored, incrementally-updated counter (no risk of it drifting out of
sync with the proposals it's meant to summarize) — it's derived fresh, under the lock, by summing live
`PROPOSED`+`APPROVED` proposals' `budget_impact` each time. `budget_impact` is a Python **property**, not a stored
column (`proposed_annual_salary − baseline_salary_at_proposal` for an increase, `bonus_amount` for a bonus) —
matches `RemunerationRecord.total_remuneration`'s existing "derive it, don't duplicate it" shape.

`REJECTED` proposals never count toward utilization (they never happened); both `PROPOSED` and `APPROVED` do — a
pending proposal provisionally reserves its share of the budget the moment it's raised, which is exactly what
stops two people simultaneously proposing increases that individually fit but jointly don't.

### 2.6 Closing a cycle: still-`PROPOSED` proposals are auto-rejected, not silently orphaned and not force-approved

Considered three options: (a) block close entirely until every proposal is resolved, (b) silently leave stragglers
attached to a closed cycle, (c) auto-resolve them. (a) lets one unresponsive approver hold an entire cycle open
past its deadline, which is a worse failure mode than the gap this task is closing. (b) is exactly the "silently
orphaned" outcome the guardrail explicitly warns against — a `PROPOSED` row referencing a `CLOSED` cycle would sit
in an ambiguous, meaningless state forever. (c) picked, with the direction being **reject, never auto-approve** —
committing money nobody explicitly approved is the wrong default; rejecting merely means the proposer has to
re-raise it in a future cycle if it's still wanted, which is the safe direction for an ambiguous outstanding
decision about pay. `close_cycle` locks the cycle, rejects every still-`PROPOSED` proposal via the existing
`reject_proposal` service function (which already notifies the proposer — no new plumbing needed), then flips
`status → CLOSED`. No new field distinguishes "a human explicitly rejected this" from "the cycle closed underneath
it" — the timestamp coincidence with `CompCycle.closed_at`, plus `CompProposal.history` (already `simple_history`),
is enough to reconstruct which happened, the same way this codebase leans on `history`/audit trails elsewhere
rather than adding a dedicated reason field for every distinct event shape. Recorded as a known, deliberate
economy, not an oversight (§7).

Proposals may only be **created** against an `OPEN` cycle (not `DRAFT`, not `CLOSED`) — enforced in
`propose_compensation_change`.

### 2.7 Data-quality check: `COMP_CYCLE_OVERDUE`, not "exceeds budget"

An "exceeds cycle budget" check was considered and rejected as **duplicative**: `exceeds_cycle_budget` is already
a live flag directly on the proposal, visible the moment it's created — unlike every other data-quality check in
this codebase, which exists specifically because the underlying state *isn't* otherwise surfaced anywhere. A new
`DataQualityException` for something the object itself already displays would just be noise.

Instead: `cycle_overdue_handler` (`compensation/data_quality.py`, new `ExceptionType.COMP_CYCLE_OVERDUE`) — mirrors
`stale_proposal_handler`'s exact shape. For every `CompCycle` still `OPEN` whose `period_end` has passed, every
`PROPOSED` proposal in it is flagged (attached to the proposal's own `employee`, same attachment target
`stale_proposal_handler` already uses) with a detail naming the overdue cycle. This is a genuinely new signal —
nothing today tells hr_admin "this review round's window has closed but people still haven't decided everything"
— and costs almost nothing to add given the existing handler to copy.

### 2.8 Performance context surfaces on the proposal, read-only, never a formula input

Per the brief's point 7 and the calibration/360 spec's own guardrail (never auto-drive money from a rating without
a human decision in between): `CompProposalSerializer` gains a read-only `performance_context` field, populated
from the **already-existing** `performance/queries.py::latest_final_score(employee_id)` seam (built for
succession, §2.7 of that spec — this is its second caller, no changes needed to the seam itself). It shows on
every proposal row a comp_manager/hr_admin already sees (`CompProposalsPage.tsx` gains a "Latest rating" column) —
informational context for the person deciding an increase, never read by `propose_compensation_change` or any
budget arithmetic. Judged worth the ~10 lines it costs given the read seam already exists and the brief invited
it explicitly; not wired into the *new-proposal form* as a suggested percentage or default, which would blur the
"informational, not a driver" line into an actual formula input.

---

## 3. The load-bearing decision: total-rewards self-scope carve-out

### 3.1 Why this module's existing posture doesn't just extend

`compensation/models.py`'s docstrings are explicit and were taken seriously: `CompProposal` is "gated entirely by
row-scope ... module-wide, catalog included," and `Benefit`'s catalog is deliberately gated the same way "rather
than treated as an open-read reference table ... this sprint's acceptance criterion is stricter, with no
carve-out for catalog data." `PayBand` and `CompProposal` additionally require `RequiresPayrollStepUp` — a live
TOTP code plus a stated business justification — on top of the role check, because they carry genuine pay figures
about *other* people. A total-rewards statement is a fundamentally different disclosure in kind: **an employee's
own confirmed current pay and their own elected benefits, shown to themself** — the same category of thing
`MyProfilePage.tsx`/`MyBenefitsPage.tsx`/`MyPerformancePage.tsx` already show for every other domain in this
system. Confirmed by grep that this doesn't already exist anywhere: no salary-adjacent field appears in
`MyProfilePage.tsx` or is exposed to the `self` row-scope in `api/types.ts` today. This is a **new** carve-out, not
an extension of an existing one, and needs to be scoped as narrowly and explicitly as the succession spec scoped
its (inverse) decision to grant **no** self-visibility at all (`docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md`
§2.6).

### 3.2 The boundary, precisely

A new endpoint, `GET /api/v1/my-total-rewards/`, resolves the acting employee **only** from the authenticated
session (`get_request_employee(request)`) — there is no `employee=` query parameter, no path parameter, no way to
ask for anyone else's statement through this surface, for any role, including hr_admin/comp_manager acting on
their own login. This is narrower even than `BenefitsElection`'s existing `IsSelfOrCompManagerOrHRAdmin` (which at
least lets a privileged role look up someone else's row) — deliberately: see §3.4 for why no privileged "view
anyone's statement" mode was built at all.

**Exposed** (all self-only, all read-only):
1. **Current salary** — the requester's own latest `RemunerationRecord` (fixed / variable / total remuneration,
   reporting period), via a new `ee_reporting/queries.py::latest_remuneration_for_employee` read seam. Source-of-
   truth reasoning in §4.
2. **Pay-band position** — the *one* `PayBand` currently valid for the requester's *own* current `job_grade`
   (`min_salary`, `mid_salary`, `max_salary`, `valid_from`), plus a computed percentile
   (`(salary − min) / (max − min) × 100`, unclamped — a figure below 0 or above 100 is shown as "below/above band,"
   not hidden, since that's real and useful information about the requester's own position). **Never** any other
   grade's band, never a historical/superseded band, never a list. This is itself new exposure — `PayBand` is
   currently gated module-wide with no carve-out at all — justified because a grade's band range is aggregate,
   grade-level information (the same shape of disclosure EEA4's median/gap stats already make to a *wider*
   audience than this), not a fact about any other *named* individual's pay. Knowing your own band's min/mid/max
   is standard total-rewards-statement content in real HR practice; it discloses the organisation's stated range
   for a grade, never what a specific colleague is paid within it.
3. **Benefits** — the requester's own `BenefitsElection` rows joined to the `Benefit` catalog. **Zero new access**
   — `MyBenefitsPage.tsx` (Sprint 15) already proves both are self-visible today; this endpoint folds the same
   data into one consolidated payload rather than requiring two separate fetches, for convenience only.
4. **Performance context** — the requester's own `latest_final_score` (via the existing `performance/queries.py`
   seam). Also zero new access — an employee already sees their own `final_score` today via
   `MyPerformancePage.tsx`'s `AgreementCard`; this is a read of something already self-visible, surfaced as
   convenience context alongside pay, not a new disclosure.

**Never exposed, via this surface, to anyone, under any role:**
- **Any `CompProposal`** — no pending or historical increase/bonus proposal, no cycle budget detail, nothing about
  a change being *considered*. A live proposal is categorically different from confirmed current pay (§3.1's
  framing, and the mirror of succession's own "absence/presence of a decision about you is itself sensitive"
  reasoning, §2.6 of that spec) — showing an employee a proposed number that hasn't been approved (or has been
  approved but hasn't synced to SAP yet, §4) risks setting an expectation the organisation hasn't committed to,
  and leaks in-flight cycle budget dynamics to the person whose own raise is what's consuming that budget.
- **Any other employee's** remuneration, band position, or benefits — structurally impossible through this
  endpoint (no id parameter exists to pass), not merely permission-denied.
- **Any `PayBand` for a grade other than the requester's own current one** — never a list, never another grade's
  figures, even in aggregate.
- **`CompCycle` details** (budget totals, department scope, utilization) — not exposed via this surface at all.
- **No `RequiresPayrollStepUp` gate.** Step-up exists specifically for the friction that should sit in front of
  *privileged access to someone else's* Restricted-tier pay data (its own docstring: "layered ON TOP OF a
  module's normal role-based permission class"). Self-view of your own data is not that — none of
  `MyProfilePage.tsx`/`MyBenefitsPage.tsx`/`MyPerformancePage.tsx` require it either, despite each touching
  Sensitive-or-Restricted-tier fields in the self-view case. Requiring step-up here would misapply a control
  designed for insider-threat mitigation against other people's data to a person looking at their own.

### 3.3 Partial statements, not a hard failure

If the requester has no `RemunerationRecord` at all yet (a new hire before the first SAP payroll extract lands),
the endpoint returns `salary: null` and `pay_band_position: null` — the rest (benefits, performance context)
still renders. A missing payroll figure doesn't make the rest of the statement meaningless, so this is a partial
200, not a 404.

### 3.4 No privileged "view any employee's statement" mode — deliberately not built

A tempting extension: let comp_manager/hr_admin pull up *any* employee's consolidated statement for a pay-review
conversation. Deliberately not built. `RemunerationRecordPermission` (`ee_reporting/permissions.py`) currently
gives comp_manager **zero** access to `RemunerationRecord` at all — `READ_ROLES = ("hr_admin", "auditor")` only,
by explicit prior design ("RBAC-Roles.md gives ee_manager 'no pay access'" — and comp_manager isn't in this
endpoint's read list either, a narrower table than `PayBand`/`CompProposal` get). Building a second,
privileged-viewer mode into this endpoint would either (a) silently widen `RemunerationRecord`'s access table as
an unplanned side effect of an unrelated feature, or (b) need its own separate access decision entirely — neither
of which this task's brief asked for. hr_admin already has full, direct access to `RemunerationRecord`, `PayBand`,
`CompProposal`, and `BenefitsElection` independently through their existing endpoints; nothing about a pay
conversation is blocked by this endpoint staying self-only. Recorded as a known boundary (§7), not a gap.

---

## 4. Current-salary source of truth: `RemunerationRecord`, not `CompProposal`

`PayBand`'s own docstring settles this: *"ADR-006: HCM masters pay bands and comp proposals; actual pay stays in
SAP."* `RemunerationRecord` is explicitly the SAP-sourced record of *actual* remuneration (its own docstring: "No
real SAP payroll integration exists yet ... populated via CSV import ... the same 'build the seam, defer the
vendor' pattern"). Checked how `ee_reporting`'s EEA4 generation already treats it before assuming
(`aggregation.py::_remuneration_for_period`, `services.py::_build_eea4_data`) — it's read as the authoritative
per-period actual figure for statutory reporting, never cross-checked against `CompProposal`, confirming the
existing system already treats `RemunerationRecord` as ground truth for "what does this person actually earn,"
not a candidate the design has to newly invent.

`CompProposal`, even `APPROVED`, is a **workflow record of an intended change**, not a payroll fact — HCM masters
the *decision*, but the number an employee is actually paid doesn't change until it lands in SAP's next extract
and appears as a new `RemunerationRecord` row (there's no live SAP integration, so this gap is real and can be
days-to-weeks wide in practice, per ADR-006's own noted future Sprint 12b interface). Reading `CompProposal` as
"current salary" would show an employee a number payroll hasn't started paying yet, which is a worse and more
confusing failure mode than being one reporting cycle behind reality. **Decision**: "current salary" always means
the latest `RemunerationRecord` by `period_end`; `CompProposal` remains strictly "what's being proposed to
change it," never conflated with "what it currently is," anywhere in this feature.

---

## 5. Data model

### 5.1 `compensation.CompCycle`

```
name            CharField, unique — e.g. "FY2026 Annual Review"
period_start    DateField
period_end      DateField
budget_amount   DecimalField(14,2) — total currency pool (§2.2)
department      FK core_hr.Department, null/blank, PROTECT — org-wide when null (§2.3)
status          CharField, choices draft/open/closed, default draft
created_by      FK Employee, null/blank, SET_NULL
closed_by       FK Employee, null/blank, SET_NULL
closed_at       DateTimeField, null/blank
history         HistoricalRecords()
```
Constraints: `period_end > period_start`; `budget_amount >= 0`. `department` is `PROTECT` (a department shouldn't
be silently deletable out from under a cycle's budget scope, matching `Position`/`CriticalPost`'s own reasoning
for `PROTECT` on a referenced scoping object).

### 5.2 `compensation.CompProposal` (extended)

```
proposal_type               CharField, choices increase/bonus, default increase
proposed_annual_salary      DecimalField(12,2), NOW null/blank (was required) — set iff type=increase
bonus_amount                DecimalField(12,2), null/blank — set iff type=bonus
baseline_salary_at_proposal DecimalField(12,2), null/blank — snapshotted RemunerationRecord.fixed_remuneration
                            at proposal time (increase only; §2.5), same snapshot posture as current_job_grade
cycle                       FK CompCycle, null/blank, PROTECT, related_name="proposals"
exceeds_cycle_budget        BooleanField, default False — refreshed at approval time (§2.5)
```
New constraint `comp_proposal_amount_matches_type` (§2.4). `budget_impact` is a **property**, not a column:
`bonus_amount` for a bonus, `proposed_annual_salary − baseline_salary_at_proposal` for an increase (`None` if no
baseline was captured).

### 5.3 `core_hr.DataQualityException.ExceptionType`

New value `COMP_CYCLE_OVERDUE = "comp_cycle_overdue"` (§2.7).

---

## 6. Access control

| Surface | Read | Write |
|---|---|---|
| `CompCycle` | comp_manager · hr_admin | comp_manager · hr_admin |
| `CompProposal` (unchanged) | comp_manager · hr_admin | comp_manager · hr_admin |
| `GET /my-total-rewards/` | the requester, self only, no exceptions (§3) | n/a (read-only) |

`CompCycleViewSet` uses the existing `IsCompManagerOrHRAdmin` — **no** `RequiresPayrollStepUp`. Reasoning: a cycle
row (name, dates, a budget total, a department, a status) carries no individual's pay figure — it's a planning
envelope, categorically different from `PayBand` (a grade's actual min/mid/max) or `CompProposal` (one named
person's proposed salary), the two models Data-Dictionary.md tiers Restricted and that earned the step-up
requirement for exactly that reason. Treated as an ordinary Internal-tier, role-gated domain object, the same
posture most of this system's module-scoped objects already have. `/my-total-rewards/` needs no dedicated
permission class — same convention `ee_reporting.dashboards::equity_dashboard` already uses (`IsAuthenticated`
plus an inline `get_request_employee` check), since the self-scoping is absolute and needs no role branching at
all.

---

## 7. Known boundaries

- **No privileged "view any employee's total-rewards statement" mode** (§3.4) — self-only, full stop; a real,
  deliberate limitation, not a gap, since building it would either silently widen `RemunerationRecord`'s existing
  access table or need its own separate decision this task wasn't asked to make.
- **No distinguishing field between "a human rejected this proposal" and "the cycle closed underneath it"**
  (§2.6) — reconstructable from `CompCycle.closed_at` vs. `CompProposal.history` timestamps; a dedicated field
  would be a small, easy addition later if that reconstruction ever proves too indirect in practice.
- **No payroll-relative (%) budget option** (§2.2) — flat currency pool only; additive later, not a breaking
  change.
- **Performance context is read-only display, never a suggested increase % or formula input** (§2.8) — a
  deliberate limitation matching the calibration/360 spec's own guardrail, not an oversight.
- **A cycle's `department` scope is enforced at proposal-creation time only** — an employee who transfers
  departments mid-cycle after their proposal was already created is not retroactively evicted from it; the
  in-scope check is a creation-time gate, not a continuously-enforced invariant, matching how `current_job_grade`
  is already a snapshot rather than a live reference elsewhere on the same model.
