# Succession Planning / Talent Pools — Design Spec

C6 (`ROADMAP-2026-08.md`: "Talent depth (pick per demand)... Succession/talent pools + career paths (on
`Position`)... §7.3 #18-24. Depends on: C1, PC-3." Both dependencies are shipped.) `NEXT_AGENT_BRIEF.md` §7.3
#18: *"Succession planning / talent pools / career paths — no critical-post flag, no readiness rating, no
successor lists. Ties naturally to Position (10) and to the skills inventory that already exists."*

This is the second C6 sub-item shipped (after mandatory-training compliance, 2026-08-25) — a talent-depth pick,
not a demoable-lifecycle break; the product owner explicitly asked to work through C6's remaining sub-items one
at a time, and named this one first.

---

## 1. The problem

Today, if the Head of Finance resigns, nothing in the system knows that seat is even *supposed* to have a
backup plan, let alone who it is. `establishment.Position` already models the seat itself (post-numbered,
approved-vs-filled, current occupant derived from `EmployeeVersion`) and `learning.EmployeeSkill` already
models what people can do — but nothing connects "this specific seat matters enough to plan for its
continuity" to "here is who we're developing to fill it, and how ready they are." Three things are
structurally impossible today:

1. **"Which posts are we most exposed on if the incumbent leaves?"** — no concept of a post being
   succession-critical at all.
2. **"Who's in the pipeline for post X, and are they actually ready?"** — no successor list, no readiness
   classification.
3. **"What's this employee's own succession story?"** — from an HR admin looking at one employee's record,
   no way to see which critical posts they've been identified as a potential successor for.

## 2. Structural decisions

### 2.1 New app: `succession`

Considered folding this into `establishment` (where `Position` lives) or `learning` (where the skills
inventory the brief points to lives), matching how mandatory-training compliance folded into `learning` rather
than becoming a new app. Rejected both, for a reason specific to this feature rather than a general preference
for new apps:

- **`establishment` is `SHARED_KERNEL`** (`rbac_audit/test_module_boundaries.py`) — `core_hr` and
  `recruitment` both hold direct FKs into it (`EmployeeVersion.position`, `Requisition.positions`), which is
  *why* it joined the kernel: infrastructure every domain app may depend on, that itself depends on nothing
  domain-shaped. Succession planning is the opposite: a single talent-management concern that needs to read
  `establishment.Position` (fine — the kernel allows that) but that nothing else in the system needs to hold a
  *reverse* dependency on. Adding succession's models directly to `establishment` would put politically
  sensitive talent data (who is/isn't a successor candidate) inside a module every other app can freely import,
  which is a strictly worse access-control position than keeping it behind its own app boundary with its own
  narrow permission classes. `establishment` gains nothing from carrying it, and the kernel gets a reason to
  grow that has nothing to do with why it's a kernel.
- **`learning` is a normal domain app, not kernel** — folding succession in there would be the same shape
  decision mandatory-training compliance made, but the content is a poor fit: `learning`'s existing domain is
  "catalogue of things a person can learn/hold" (`Skill`, `Course`) plus records of them holding it
  (`EmployeeSkill`, `TrainingRecord`). Succession planning isn't about a catalogue of learnable things; it's
  about seat continuity for specific establishment posts. The only real connection is that readiness is
  *informed by* an employee's skills — which a `queries.py` read seam handles perfectly well (§2.4) without
  merging two conceptually distinct domains into one app the way `Course`/`CourseRequirement` genuinely did
  belong next to `Skill`/`EmployeeSkill`.

A new `succession` app, importing `core_hr` (`Employee`) and `establishment` (`Position`, both kernel — direct
FKs allowed) directly, and reading `learning`/`performance` (both ordinary domain apps) only through their
`queries.py` seams. `rbac_audit/test_module_boundaries.py`'s `DOMAIN_APPS` list gains `"succession"`; it does
**not** join `SHARED_KERNEL` — nothing needs a direct FK into it, matching the `establishment` reasoning above
in reverse (it doesn't need kernel privileges to build this; it only needs kernel privileges *granted to it as
a consumer*, which every ordinary domain app already gets from the existing kernel membership rule).

### 2.2 Scoping decision: tied to `Position`, not a broader "role/career track"

The brief explicitly flagged this as worth checking against the mandatory-training-compliance precedent
(`Department` + `OccupationalLevel`, both optional). Investigated and rejected for this feature specifically:

- **A critical post is inherently one specific seat, not a category of seats.** "The Head of Finance role
  needs a succession plan" names *one* post (`post_number` P-00042), not "everyone at Senior Management
  level in Finance." Two different Senior-Management posts in different departments are not interchangeable
  succession targets — someone ready to step into the CFO seat isn't thereby a candidate for Head of
  Engineering just because both happen to sit at the same `OccupationalLevel`. Mandatory training's
  Department/OccupationalLevel scoping works precisely *because* a training obligation genuinely does apply to
  a whole population uniformly ("everyone in Senior Management must complete the Code of Conduct refresher");
  succession planning's whole premise is the opposite — continuity for one named seat.
- **`Position` already carries the "role type" context a broader scope would add**, without inventing a
  separate taxonomy: every `Position` already has `department`, `occupational_level`, and `job_grade`. A
  critical-post list filtered/grouped by those fields already answers "which Senior Management posts are
  succession-critical," with no new scoping model needed.
- **The brief's own "career path" requirement (§2.5 below) is satisfied by a list of positions**, each already
  self-describing via its own department/level/title — a successor candidate's "career path" is legible as
  "here are the critical posts you've been identified against," without needing an abstract career-track
  object layered on top.

Decision: `succession.CriticalPost` has a `OneToOneField` to `establishment.Position` (one row per post that
has ever been flagged critical; `active` toggles the flag without losing history — see §4.1). A broader
"pool for a role/career track not tied to one seat" was considered a real, valid HR concept but **deliberately
not built** — it would need its own scoping-axis decision (department/level again? job family, which doesn't
exist as a structured field anywhere in the system yet?) and the brief's own worked example (§7.3 #18) frames
the gap entirely in terms of critical posts and successor lists, not broader career tracks. Recorded as a
known boundary (§8), not an oversight — a natural, low-risk future extension if a real broader-pool need shows
up (the `SuccessionCandidate` model, named generically rather than `PositionSuccessionCandidate`, would not
need renaming to support it).

### 2.3 `CriticalPost.active` — flag/unflag preserves history, mirrors `Course.active`/`CourseRequirement.active`

A post stops being succession-critical sometimes (reorganisation, the risk that justified flagging it is
resolved) — `active=False` retires the flag without deleting the row, so the fact it was once flagged (and
why) stays on the record, same convention as `Skill.active`/`Course.active`/`CourseRequirement.active`.
Existing `SuccessionCandidate` rows against an unflagged `CriticalPost` are **not** cascade-deactivated —
they simply stop appearing in the "currently critical" default view (frontend/data-quality both filter on
`CriticalPost.active`); if the post is re-flagged later, its prior nomination history is still there rather
than having been silently destroyed by the unflag action. `position` is a `OneToOneField` (unique) rather than
allowing multiple `CriticalPost` rows per position over time — one lineage per post, toggled, not a growing
list of flag/unflag cycles — which keeps "is this post currently critical" a single unambiguous row to look
up rather than "the most recent row for this position."

### 2.4 No `services.py` — every write is single-row, validated in the serializer

`establishment`'s `Position`/`PositionApprovalStep` and `onboarding`'s `ChecklistTemplate`/`ChecklistInstance`
both needed a `services.py` because they're genuine state machines (an approval chain stepping through roles in
order; a template version lifecycle). Succession planning has no such machine: flagging a post critical is one
row write with one validation rule (§4.1); nominating, updating, or withdrawing a candidate is one row write
with a couple of validation rules (§4.2). This is exactly the shape `learning.Skill`/`Course`/
`CourseRequirement` already have, and they don't have a `services.py` either — validation lives in each
serializer's `validate()`, the same place `CourseRequirementSerializer` already checks for a duplicate active
scope. The guardrail "`transaction.atomic` in multi-row service writes" doesn't add anything here because
there are no multi-row writes to protect — recorded as deliberately-not-needed, not skipped.

### 2.5 Career paths: a read-only section on `EmployeeDetailPage.tsx`, not a new page

The brief asks for "a lightweight way to see what pool(s) is this employee in, for what post(s)/track(s) —
decide whether a dedicated page or a section on the existing `EmployeeDetailPage.tsx` is the right surface."
Decision: a section on `EmployeeDetailPage.tsx`, matching every other per-employee rollup already there
(Skills, Certifications, Training, Goals, Documents, Dependants). A standalone page would either have to be
org-wide (which the Talent Pools management page — §5.3 — already is, and would duplicate) or need its own
employee-picker to become single-employee, which is exactly what navigating to that employee's detail page
already does for free. This section is **read-only** and **hr_admin/auditor-only**, matching who can read
`SuccessionCandidate` at all (§5.2) — see §2.6 for why it does not appear when an employee views their own
record.

### 2.6 Access-control decision: nobody sees their own succession status, full stop

This is the decision the brief most explicitly asked to be thought through rather than defaulted. The
"obvious" default for an ESS-heavy system like this one is self-visibility — almost everything else on
`EmployeeDetailPage.tsx`/the `/my-*` pages is visible to the employee it's about. Succession data is
different in kind, not just degree:

- **A successor list is a comparative, exclusionary judgement about *other* people, made visible to the
  subject.** Telling someone they're flagged "development needed" against a specific post, or — worse —
  that a colleague is listed as "ready now" for a seat they might have wanted, is a substantially different
  disclosure than "here is your own skill/training record," which is purely about the viewer themself.
  RBAC-Roles.md's existing standing rules already draw exactly this line for aggregate demographic data
  (small-cell suppression protects against re-identifying *someone else* inside a cell you can see); this is
  the same shape of risk at the level of a single named list rather than a statistical aggregate.
- **Absence is itself sensitive, not just presence.** An employee who checks their own record and finds they
  are *not* listed against any critical post has been told something ("you're not seen as ready, or not
  considered at all") that HR has not chosen to communicate to them directly, through whatever channel (a
  development conversation, a PDP) HR would normally use for a message like that. A visible-but-empty section
  is not neutral the way an empty Documents list is.
- **No RBAC-Roles.md precedent grants this.** `line_manager`'s "sees own team's reviews/goals" carve-out is
  explicit and narrow; nothing in the existing role table extends *any* role's self-scope to a second-order
  judgement about future-role suitability. Extending self-visibility here would be inventing a new precedent,
  not applying an existing one.

Decision: **no role sees their own row as the subject of a `SuccessionCandidate`, including the employee
themself, their own line_manager, and hr_admin acting on their own record** — read access is `hr_admin` and
`auditor` only, full stop, with no self-scope carve-out at all (§5.2). This is stricter than a normal
Internal-tier field (which the base `employee` role reads for itself by default) and stricter than the
Sensitive-tier pattern (which the base role also reads for itself, e.g. `race`/`gender`) — deliberately, per
the brief's own steer that this is more sensitive than a typical Internal-tier field, not less. The
`CriticalPost` flag itself (§4.1, §5.1) is a materially smaller disclosure — "this seat is important" says
nothing about any named person — so it stays visible to the same audience that can already see `Position` at
all (hr_admin, comp_manager, accounting_officer, auditor, recruiter), matching `establishment`'s own precedent
table in `RBAC-Roles.md` exactly.

A manager-nominates/hr_admin-confirms two-step workflow was also considered (mirroring `Position`'s
propose→approve chain) and set aside: the brief frames this as "nominate," not "propose then approve," and
`hr_admin` already single-handedly manages workforce-planning objects of comparable sensitivity elsewhere in
the system (`ChecklistTemplate`, `Course`/`CourseRequirement`) without a second approver. Line managers are
frequently the people with the clearest view of who's actually ready — a real limitation of hr_admin-only
authorship — but building a nomination-intake workflow for that input (vs. just having HR ask the manager and
type it in themselves, which is how this kind of conversation happens today with no system at all) is scope
this slice doesn't need; recorded as a known boundary (§8), not a gap that was missed.

### 2.7 Cross-app read seams: `learning/queries.py` and a new `performance/queries.py`

Per the brief's own steer (readiness should be able to reference skills/performance without importing peer
models directly):

- **`learning/queries.py`** gains `skill_names_for_employee(employee_id)` — the catalogue names of skills an
  employee currently holds, one query, read-only. Used purely as informational context on a candidate's card
  (§5.3) — never read by, or fed into, the readiness classification itself (§4.2 is explicit that readiness is
  always a human judgement call, recorded, not computed).
- **`performance/queries.py` is a new file** — `performance` had no read seam before this (nothing needed one).
  Gains `latest_final_score(employee_id)`, returning the most recent `PerformanceAgreement` with a frozen
  `final_score` (set once the Head signs the FINAL stage — `performance/services/agreements.py::
  _finalize_scoring`) plus its period name and `hr_attention` flag, or `None` if the employee has no scored
  agreement yet. Same posture as the skills seam: informational context only, never an input to the stored
  readiness value. `rbac_audit/test_module_boundaries.py`'s `test_every_queries_seam_is_read_only` covers it
  automatically (it walks every app's `queries.py`, not a hardcoded list).

Both are called once per `SuccessionCandidate` row when serializing (small dataset by nature — a handful of
critical posts, each with a handful of candidates, is the realistic scale for this feature; this is explicitly
**not** the `/employees`-list-at-153-rows shape the N+1 guardrail exists to protect against, so a per-row call
through a narrow, single-employee seam function was judged acceptable rather than worth a batching interface
that has no realistic caller needing it yet).

### 2.8 Readiness vocabulary: four bands, not a 9-box grid

`ready_now` / `ready_1_2_years` / `ready_3_plus_years` / `development_needed` — exactly the brief's own
suggested vocabulary, which is standard succession-planning shorthand (a simplified read along the "readiness"
axis of the classic performance/potential 9-box, without building the potential axis, the performance axis, or
the grid itself). A full 9-box (crossing this readiness axis against a separate potential rating) was
considered and set aside: nothing in the brief or the existing system asks for a "potential" rating as a
distinct concept from performance (which `performance/queries.py`, §2.7, already surfaces as context), and
building a second rating axis with no consumer would be speculative scope. If a future session needs the full
grid, `latest_final_score` already gives the performance axis for free; only a potential axis would need
adding.

### 2.9 Data-quality check: critical post with no ready-now/ready-soon successor

Registered the same way every other C-series check has been (`core_hr.data_quality.register()`, called from
`succession.apps.SuccessionConfig.ready()`). Iterates active `CriticalPost` rows; a post whose active
`SuccessionCandidate` set contains no `ready_now`/`ready_1_2_years` row is flagged. The handler contract
requires an `Employee` to attach the exception to (`core_hr/data_quality.py`'s own docstring: "yield (employee,
detail)") — attached to the post's **current occupant**, since they're the person whose eventual departure
creates the continuity risk this check exists to surface. A critical post that is currently **vacant** has no
occupant to attach the exception to and is silently skipped by this check — not a gap: a vacant critical post
is already visible on `/positions` (it shows as vacant to everyone who can see the post at all), so the
information isn't lost, just not duplicated into a second exception type for the same underlying fact.

A richer version — "flag a critical post whose *sole* ready successor is themselves flagged overdue/at-risk
elsewhere" — was suggested in the brief's context list as a "useful" enrichment, not part of the minimum scope,
and is recorded as a known boundary (§8) rather than built now: it would mean querying every other app's open
`DataQualityException` rows for each candidate, a cross-cutting join that's easy to add later (core_hr already
owns `DataQualityException` so no new seam would even be needed) but adds real complexity for a scenario the
brief itself didn't ask to be built this round.

---

## 3. Recorded decisions (quick-reference)

1. New app `succession`, not folded into `establishment` (kernel — would over-expose sensitive data to every
   importer) or `learning` (wrong domain fit) (§2.1). Not `SHARED_KERNEL` — nothing needs a reverse FK into it.
2. Scoped to `establishment.Position` via a `OneToOneField`, not a broader Department/OccupationalLevel "role
   track" the way `CourseRequirement` is — a critical post is one specific seat, not a population (§2.2).
3. `CriticalPost.active` flags/unflags without deleting, mirroring `Skill.active`/`Course.active` (§2.3).
4. No `services.py` — single-row writes, validated in each serializer, matching `Skill`/`Course`/
   `CourseRequirement`'s shape rather than `Position`'s/`ChecklistTemplate`'s workflow shape (§2.4).
5. Career-path view: a read-only section on `EmployeeDetailPage.tsx`, hr_admin/auditor-only, not a new page
   and not self-visible (§2.5).
6. **Access control: nobody sees their own succession status — no self-scope carve-out at all, for anyone,
   including hr_admin viewing their own record.** Read is `hr_admin`/`auditor` only for the successor-candidate
   data; the coarser `CriticalPost` flag itself is visible to the same audience `Position` already is
   (hr_admin, comp_manager, accounting_officer, auditor, recruiter) (§2.6).
7. `learning/queries.py::skill_names_for_employee` and a new `performance/queries.py::latest_final_score` —
   read-only context on a candidate's card, never an input to the stored readiness value (§2.7).
8. Readiness vocabulary: `ready_now` / `ready_1_2_years` / `ready_3_plus_years` / `development_needed` — no
   9-box grid (§2.8).
9. Data-quality check `CRITICAL_POST_NO_SUCCESSOR`: active critical post with no active ready-now/ready-soon
   candidate, attached to the post's current occupant; a vacant critical post is silently skipped (already
   visible via `/positions`) (§2.9).

---

## 4. Data model

### 4.1 `succession.CriticalPost`

```
position       OneToOneField establishment.Position, PROTECT, related_name="critical_post_flag"
reason         TextField, blank — why this post is succession-critical (free text; no controlled vocabulary
               was asked for and the reason is read by a narrow, already-privileged audience, §5.1)
active         BooleanField, default=True — flag/unflag without deleting (§2.3)
flagged_by     FK core_hr.Employee, null, blank, SET_NULL, related_name="critical_posts_flagged"
history        HistoricalRecords() — full change trail (who flagged/unflagged/re-reasoned, when); this data's
               sensitivity (§2.6) justifies the same audit-trail investment `Position`'s own approval-sensitive
               fields already get, even though the write pattern here is much simpler than an approval chain
```
`PROTECT` on `position` (not `CASCADE`) — matches `EmployeeSkill.skill`'s own reasoning for `PROTECT`: a
`Position` shouldn't be silently deletable while a critical-post flag (and its nomination history) still
references it. In practice `Position` rows are never hard-deleted in this system (rejected/retired posts stay
as rows with a status), so this is a defensive constraint rather than one expected to bite in normal use.
`CriticalPostSerializer.validate()` rejects a `position` whose `status != Position.Status.APPROVED` — a
draft/in-review/rejected post isn't a real seat yet, mirroring `CourseRequirementSerializer.validate()`'s
"must target a `mandatory=True` course" shape (reject a nonsensical target at the boundary, not downstream).

### 4.2 `succession.SuccessionCandidate`

```
critical_post   FK CriticalPost, CASCADE, related_name="candidates" — CASCADE (not PROTECT): a CriticalPost row
                is never hard-deleted either (unflag via `active`, §2.3), so this only fires if a post is force-
                deleted at the DB/admin level, at which point its nomination history has no meaningful home left
employee        FK core_hr.Employee, CASCADE, related_name="succession_nominations"
readiness       CharField, choices (ready_now / ready_1_2_years / ready_3_plus_years / development_needed) (§2.8)
notes           TextField, blank — free-text HR context (development areas, conditions on readiness, etc.)
nominated_by    FK core_hr.Employee, null, blank, SET_NULL, related_name="succession_candidates_nominated"
active          BooleanField, default=True — withdraw without deleting; multiple historical (inactive) rows
                for the same (critical_post, employee) pair are allowed (a real re-nomination-after-withdrawal
                scenario keeps its own full history rather than being collapsed into one reactivated row)
history         HistoricalRecords() — readiness/notes changes over time are exactly the kind of thing "was this
                person's readiness re-assessed, by whom, when" needs a trail for
```
Constraints: `UniqueConstraint(fields=["critical_post", "employee"], condition=Q(active=True),
name="one_active_nomination_per_post_per_employee")` — mirrors `ChecklistInstance`'s
`one_active_checklist_per_employee_per_direction` shape exactly: at most one *active* nomination per pair,
any number of historical ones. `SuccessionCandidateSerializer.validate()` additionally rejects:
- a `critical_post` that isn't currently `active` (§2.3 — can't nominate against an unflagged post);
- `employee` being the post's own current occupant (`critical_post.position.current_occupant`, if any) — you
  can't be your own successor;
- a duplicate active pair (the same check `CourseRequirementSerializer` already does for its own uniqueness
  gap, since `NULL != NULL` semantics don't help here either — `condition=Q(active=True)` is a real DB
  constraint this time, but the serializer check exists to turn what would otherwise be a raw
  `IntegrityError` → 500 into a clean 400, same reasoning as everywhere else in this codebase that pairs a DB
  constraint with an application-level pre-check).

---

## 5. Access control

### 5.1 `CriticalPost`

Read: **hr_admin · comp_manager · accounting_officer · auditor · recruiter** — identical to `Position`'s own
read table in `RBAC-Roles.md` (§2.6 — the flag is Position-adjacent metadata, not the sensitive nominee list).
Write (create/update): **hr_admin only**. Enforced by `CriticalPostPermission`
(`READ_ROLES`/`WRITE_ROLES` class attributes, same shape as `ChecklistTemplatePermission`).

### 5.2 `SuccessionCandidate`

Read and write: **hr_admin only manages it; hr_admin and auditor may read it. No other role, including the
employee themself and their line_manager, may read it at all** (§2.6) — enforced by
`SuccessionCandidatePermission`. Deliberately **not** a `FIELD_TIERS`/`TieredModelSerializer` entry — matches
`performance.Review`/`Feedback`'s own documented exception in `rbac_audit/tiers.py` ("gated by whole-endpoint
role/row checks instead," since the model itself, not a subset of its fields, is what's sensitive here, and
the coarse permission class already excludes everyone outside hr_admin/auditor from reaching a read at all).

### 5.3 Frontend surfaces

- **Talent Pools page** (new, hr_admin-only route `/talent-pools`) — the management view: list critical posts
  (with a "flag a position as critical" form drawing from the existing approved-positions list), and per post,
  its successor candidates (nominate/update readiness/withdraw), each candidate card showing the
  `skill_names_for_employee`/`latest_final_score` context from §2.7.
- **Positions page** (`PositionsPage.tsx`, existing route, existing role gate) — gains a "Critical" column
  reading from `/critical-posts/` (fetched client-side alongside `/positions/`, same cross-referencing pattern
  `CourseCataloguePage.tsx` already uses joining `/courses/` and `/course-requirements/` locally) — visible to
  everyone who can already see the Positions page (§5.1's read audience), since that's the same audience.
- **Employee detail page** (`EmployeeDetailPage.tsx`, existing route) — a new, **read-only** "Succession"
  section, rendered **only when the viewer holds hr_admin or auditor** (checked client-side via `hasRole`,
  same pattern every other role-gated section on this page would use if one needed it — the real gate is
  server-side, §5.2, so a stray render attempt by an unauthorised role would just get an empty/403'd response,
  not a data leak) — listing which critical posts this employee is an active candidate for for and their
  recorded readiness. **Never rendered when `employeeId === user?.employee_id`** (viewing your own record) even
  for an hr_admin, so the "never self-visible" decision (§2.6) holds even for the one role that could otherwise
  technically read the data about themself.

---

## 6. Testing

Mirrors `learning/tests.py` + `learning/test_api.py`'s shape:
- Service/model-level: `CriticalPost` flag/unflag preserves history; `position` must be `APPROVED` to flag;
  `SuccessionCandidate` create/withdraw/re-nominate cycle; the active-uniqueness constraint; the
  can't-nominate-the-current-occupant rule; the can't-nominate-against-an-inactive-post rule.
- API/role-matrix: `CriticalPost` read open to the `Position`-read role set, write hr_admin-only, every other
  role 403; `SuccessionCandidate` read/write hr_admin-only, auditor read-only, every other role — including
  `line_manager` and the nominated employee's own login — 403 on both list and retrieve.
- `learning/queries.py::skill_names_for_employee` and `performance/queries.py::latest_final_score` — direct
  unit tests (empty case, populated case) plus `rbac_audit/test_module_boundaries.py`'s existing
  `test_every_queries_seam_is_read_only` sweep picking up the new seam automatically (no test change needed
  there — it walks every app's `queries.py` file, not a hardcoded list).
- `succession/test_data_quality.py`: `CRITICAL_POST_NO_SUCCESSOR` opens for a critical post with no
  ready-now/soon candidate, resolves once one is added, and is silently absent for a vacant critical post —
  mirrors `learning/test_data_quality.py`'s register/run/assert shape.
- e2e: a new `succession.spec.ts` — hr_admin flags a post critical, nominates a candidate, sees it on the
  Positions page's Critical column and the candidate's Employee Detail page; a non-hr_admin/auditor login
  (e.g. `manager`) gets no Talent Pools nav item and a 403 hitting the API directly; the nominated employee's
  own login sees no succession section on their own detail page even if they separately hold hr_admin (tested
  by asserting the section's absence when `employeeId === own id`, not just role-gating).

---

## 7. Known boundaries

- **No broader "role/career track" pool independent of a specific critical post** (§2.2) — a real, valid HR
  concept, deliberately not built this round; the model naming leaves room for it later without a rename.
- **No manager-nominates/hr_admin-confirms two-step workflow** (§2.6) — hr_admin authors nominations directly,
  the same single-actor pattern `ChecklistTemplate`/`Course`/`CourseRequirement` already use. A real
  limitation (line managers often have the clearest view of readiness) accepted for this slice.
- **Unflagging a critical post does not cascade-withdraw its candidates** (§2.3) — deliberate, preserves
  history for a possible re-flag, but means an inactive post's candidate rows are only reachable by querying
  history, not visible in the default "current" views.
- **No "sole ready successor is themselves at-risk elsewhere" enrichment** on the data-quality check (§2.9) —
  suggested in the brief's context as a "useful" idea, not built; a real, low-effort future extension (no new
  seam needed, `core_hr` already owns `DataQualityException`).
- **No reminders/notifications** — unlike mandatory-training compliance, nothing in the brief's minimum scope
  asked for a nudge cadence here (there's no natural "due date" the way a training requirement has one), so no
  `succession/reminders.py`/Celery task was built. If a future need emerges (e.g. "review readiness ratings
  annually"), `notifications.services.notify_many` is a cheap, precedented addition at that point.
