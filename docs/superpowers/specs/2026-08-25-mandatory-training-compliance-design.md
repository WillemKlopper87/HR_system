# Mandatory-Training Compliance — Design Spec

C6 (`ROADMAP-2026-08.md`: "Talent depth (pick per demand)... mandatory-training compliance + course
catalogue... §7.3 #18-24. Depends on: C1, PC-3." Both dependencies are shipped.) `NEXT_AGENT_BRIEF.md` §7.3
#21: *"Learning: mandatory-training compliance, course catalogue, SETA/skills-levy tracking — training records
are free-text; no catalogue, no 'required for role' rules, no completion-rate dashboard by mandatory course."*

This is a talent-depth pick, not a demoable-lifecycle break — the five original lifecycle breaks are already
closed (`docs/SESSION-STATE.md`); leave/absence remains the only one still blocked on a product decision. This
slice was explicitly chosen next by the product owner while that decision is pending.

---

## 1. The problem

`learning.TrainingRecord.title` is a free `CharField`. Two people who both attended "POPIA Awareness
Training" and two who attended "Popia awareness" are, to the database, unrelated strings. That makes three
things structurally impossible today, not just inconvenient:

1. **"How many people have completed course X?"** — no query can group training records by course identity,
   only by exact title-string match, which real-world data entry never guarantees.
2. **"Who still owes course X?"** — there is no concept of *owing* a course at all. Nothing records that a
   given course is mandatory for anyone, so nothing can be overdue.
3. **A completion-rate dashboard by mandatory course** — impossible without (1) and (2) both existing first.

`learning.Skill`/`EmployeeSkill` already solved the identical shape of problem for skills: a catalogue
(`Skill`) the organisation defines once, and a join table (`EmployeeSkill`) recording who holds which catalog
entry. This spec applies that same shape to courses, plus a new concept skills never needed — a *requirement*
rule stating which population must hold a given catalogue entry, and by when.

---

## 2. Structural decisions

### 2.1 Extends `learning`, no new app

`Course`/`CourseRequirement` are catalogue + assignment-rule data, exactly `learning`'s existing domain
(`Skill`/`EmployeeSkill` already live here). No cross-app coupling is needed to build this — the population
scoping (§2.3) reads `core_hr.Department`/`OccupationalLevel`, which `learning` already imports directly for
`skills_inventory`'s by-department/by-level breakdown. `NEXT_AGENT_BRIEF.md`'s guardrail matches: this is
squarely inside `learning`'s existing domain, not a new peer.

### 2.2 `Course.mandatory` (catalogue metadata) is distinct from `CourseRequirement` (a scoped rule)

The brief lists both "whether it's mandatory" as a `Course` field and a separate `CourseRequirement` model.
Read literally these look redundant — if a `CourseRequirement` is what actually makes a course "required for
a population," what does the flat `Course.mandatory` boolean add? Decision: `Course.mandatory` is catalogue
metadata classifying the *kind* of course (compliance/statutory in nature vs. an ordinary elective an employee
might request through the existing self-service `TrainingRecord` flow, e.g. "AWS Bootcamp"), independent of
whether any rule currently targets a population for it. `CourseRequirement` is the actual scoped mandate.
The two are linked by a validation rule, not redundancy: **a `CourseRequirement` may only target a course with
`mandatory=True`** (`CourseRequirementSerializer.validate`) — a requirement rule on a course not flagged
compliance-type would be a contradiction the catalogue itself should prevent, not a state the UI has to notice.
This also keeps the course-catalogue page useful on its own (filter to "compliance courses" without needing
any requirement rows yet) rather than mandatory-ness only being inferable by checking for requirement rows.

### 2.3 Scoping FK choice: `Department` and `OccupationalLevel`, both optional, not `Position` or `job_title`

Investigated per `NEXT_AGENT_BRIEF.md` point 6, against `core_hr.EmployeeVersion`'s actual structured fields:

- **`job_title` (free text) — rejected outright.** The brief's own warning is correct: two people with the
  job title "Senior Engineer" and "Sr. Engineer" are, to the database, unrelated strings — the exact defect
  this feature exists to fix for training *titles*; keying a rule off an equally unreliable field would just
  relocate the problem.
- **`establishment.Position` — rejected.** A `Position` is an individually-numbered *post*
  (`post_number`, one per approved establishment slot, persists across incumbents) — "post 00234, Senior
  Engineer, Engineering" — not a role *type*. A compliance rule like "everyone in Senior Management must
  complete the Code of Conduct refresher" is not naturally expressed as a list of individual posts, and a
  rule keyed to `Position` would need updating every time a post is created or renumbered, for a concept
  (role type/seniority) `Position` doesn't represent. This is exactly the brief's flagged risk ("too
  granular — posts, not role types") confirmed by reading the model, not just deferred to.
- **`Department`, `OccupationalLevel` — chosen, both optional (nullable) FKs on `CourseRequirement`.** Both
  already exist on `EmployeeVersion` as required (non-null) structured fields, are exactly what
  `skills_inventory`'s existing by-department/by-level breakdown already groups by, and match the brief's own
  worked examples precisely: "all of Finance" is `department=Finance, occupational_level=None`; "all Senior
  Management" is `department=None, occupational_level=SENIOR` (the six EEA9 levels seeded in
  `core_hr/migrations/0002_seed_occupational_levels.py`, "SENIOR — Senior management" among them); "the
  intersection" is both set. **Both null** is also allowed and meaningful — an organisation-wide mandate (e.g.
  a POPIA-awareness or health-and-safety induction everyone must complete) is a real, common compliance
  pattern and there is no reason to force a department/level split onto something that has none. `job_grade`
  was considered and set aside: it is a pay-banding concept (`compensation.PayBand` keys off it) layered
  *under* `occupational_level`, not an independent scoping axis a training rule naturally targets — every real
  worked example in the brief (department, seniority tier) is already covered by department/level alone, and
  adding a third optional axis without a concrete driving example would be speculative scope, not a decision.

### 2.4 Compliance is derived, never stored — same philosophy as `Position.current_occupant`

`establishment.Position.current_occupant`/`is_vacant` are computed on read from `EmployeeVersion`, never
stored, so they can never drift out of sync with who's actually employed. `learning.compliance` (new module)
applies the identical philosophy: no `ComplianceRecord` table, no per-employee-per-requirement row to keep in
sync. Given an employee (or a queryset of employees) and an as-of date, it derives — fresh, every call — which
`CourseRequirement`s currently apply to them, whether an existing `TrainingRecord(course=X, status=COMPLETED)`
satisfies each one within its validity window, and if not, whether they're within the due period or overdue.
This means: adding a `CourseRequirement` retroactively "applies" to everyone already in scope with no backfill
step, exactly as intended ("rules can be added after people are already employed" — brief point 2); nothing
can ever go stale the way a stored snapshot could.

### 2.5 `TrainingRecord.course` is nullable — ad-hoc training keeps working

`TrainingRecord.course` is a new nullable FK to `Course`. Nullable specifically so ad-hoc, non-catalogue
training (an employee's self-submitted "AWS Bootcamp" via the Sprint-15 ESS flow, or any historical row) keeps
working unmodified — nothing forces every `TrainingRecord` through the catalogue, and the migration does not
attempt to backfill `course` onto historical rows (no reliable title→course mapping exists, and guessing one
would risk falsely marking someone compliant against a rule they never actually satisfied). Compliance
derivation only ever looks at `TrainingRecord.course = X`, never at `title` — a free-text "POPIA Awareness"
row completed before the catalogue existed will not retroactively satisfy a `CourseRequirement` for the POPIA
Awareness `Course`; HR would need to re-file it against the catalogue entry if that history matters. This is
recorded as a known, deliberate boundary (§9), not an oversight.

### 2.6 `wsp_atr_export` is unaffected on inspection, not extended

`learning/views.py::wsp_atr_export` already unions `TrainingRecord` (all of it, any `course` value including
null) and `Certification` into one CSV (C2, `2026-08-25-employee-documents-popia-design.md` §2.4). A
`TrainingRecord` with `course` now set is still a `TrainingRecord` row and already appears in that export
unchanged — `course` doesn't need to appear as its own CSV column for the export to keep including mandatory
training, because completed mandatory-course enrolments are ordinary `TrainingRecord` rows with `status=
COMPLETED`, already in the export's `training_records` queryset. The compliance *rules* themselves
(`CourseRequirement`) are not WSP/ATR data — a WSP/ATR submission reports what training happened, not what
policy requires; SETA doesn't want a CSV row for a rule nobody has completed yet. No change to
`wsp_atr_export` is needed. This was verified against the export's actual query (not assumed) before
concluding no extension was warranted, honouring the brief's explicit "verify... rather than assuming."

### 2.7 No `learning/queries.py` extension — the one cross-boundary consumer uses the registry seam, not `queries.py`

The only peer-app-adjacent consumer this slice has is the data-quality registry (§2.8), and that mechanism is
already a `core_hr.data_quality.register(exception_type, handler)` callback — `learning` calls `register()`
from its own `AppConfig.ready()`, `core_hr` never imports `learning`. That is a complete, working seam on its
own; routing it through `queries.py` as well would be a redundant indirection with no second caller. No
peer app currently needs org-wide mandatory-training data through a read seam (`ee_reporting` doesn't have a
training-compliance section; nothing else is training-shaped). `queries.py` is left unextended, matching this
spec's own instruction to extend it "if any peer app needs read access" — none currently does. If a future
session needs one (e.g., an EE report cross-referencing compliance), it is a small, well-precedented addition
at that point, not a corner cut now.

### 2.8 Data-quality registry entry: `MANDATORY_TRAINING_OVERDUE`

Follows `performance`/`compensation`'s existing pattern exactly (`core_hr/data_quality.py`'s module
docstring: "Registered — every other app's checks, registered from that app's own `AppConfig.ready()`").
`core_hr.models.DataQualityException.ExceptionType` gains one new choice, `MANDATORY_TRAINING_OVERDUE`
(`core_hr` migration `AlterField`, same shape as `0005_alter_dataqualityexception_exception_type.py`, which
already added `performance_overdue`/`comp_proposal_stale` the same way — editing `core_hr`'s own model to add
a registered check's exception type is the established, precedented shape, not a peer-app-boundary violation:
`core_hr` owns `DataQualityException`, every domain app already imports `core_hr` directly). `learning/
data_quality.py::overdue_training_handler` reuses `learning.compliance`'s own derivation (no re-implementation
— identical to how `performance/data_quality.py::overdue_agreement_handler` reuses `reminders.py`'s
`outstanding_agreements` rather than re-deriving "who's outstanding").

### 2.9 Reminders: a daily Celery task, riding the existing notification plumbing

`notifications.services.notify`/`notify_many` (H3) already do everything a "you have a mandatory course due"
nudge needs — in-app row unconditional, email best-effort — so this is cheap to wire, per the brief's own
"if reminders are cheap to wire through the existing Notification/email adapter, do it" steer. A new
`learning/reminders.py::run_mandatory_training_reminders` mirrors `core_hr/contract_reminders.py`'s exact-
offset-day shape (not `performance/reminders.py`'s `ReminderLog`-deduped range shape — this task's query is a
narrow "N days before due" or "just went overdue" match, run once daily, so a manual same-day re-run is the
only double-send risk, accepted for the same reason `contract_reminders.py`'s own docstring accepts it: "an
extra in-app nudge, not a duplicate decision or data change"). Registered as a new
`CELERY_BEAT_SCHEDULE["run-mandatory-training-reminders-daily"]` entry (not folded into the existing
`core_hr`-owned daily job — this task belongs to `learning`, not `core_hr`, and `core_hr.tasks`' own docstring
for why it rides the contract-reminder job is specific to two `core_hr`-owned concerns sharing one daily slot,
not a general "add everything to the one job" rule). Two nudges: the employee gets notified when their
personal due date is `MANDATORY_TRAINING_REMINDER_OFFSET_DAYS` (default 14, env-configurable, mirroring
`CONTRACT_REMINDER_OFFSETS_DAYS`'s own env-sourced pattern) away, and their manager gets notified the day a
requirement actually lapses into overdue (one event, not a range — avoids re-notifying the manager daily for
the whole time someone stays overdue; the data-quality exception and dashboard already surface the ongoing
state for anyone who checks).

---

## 3. Recorded decisions (quick-reference)

1. Extends `learning`, no new app (§2.1).
2. `Course.mandatory` (catalogue metadata) vs. `CourseRequirement` (scoped rule) — a requirement may only
   target a `mandatory=True` course, enforced in the serializer (§2.2).
3. Scoping FKs: `Department` and `OccupationalLevel` on `CourseRequirement`, both optional, both-null meaning
   organisation-wide; `Position`/`job_title`/`job_grade` all considered and rejected (§2.3).
4. Compliance is derived on read (`learning/compliance.py`), never stored (§2.4).
5. `TrainingRecord.course` is a nullable FK; no backfill onto historical rows; compliance only ever reads
   `course`, never `title` (§2.5).
6. `wsp_atr_export` needs no code change — verified, not assumed (§2.6).
7. `learning/queries.py` is not extended — the only current cross-boundary consumer uses the data-quality
   registry seam, which is already complete on its own (§2.7).
8. New `DataQualityException.ExceptionType.MANDATORY_TRAINING_OVERDUE`, registered from
   `learning.apps.LearningConfig.ready()` (§2.8).
9. A new daily Celery task (`learning/reminders.py` + `learning/tasks.py`), its own `CELERY_BEAT_SCHEDULE`
   entry, reusing `notifications.services.notify`/`notify_many` (§2.9).
10. Aggregate completion-rate dashboard: `hr_admin` only, same shape/precedent as `skills_inventory`.
    Overdue-individuals list: row-scoped via the existing `row_scoped_queryset` primitive, same shape as
    `team_development` — no new access-control mechanism invented (§5).

---

## 4. Data model

### 4.1 `learning.Course`

```
name             CharField, unique=True — catalogue identity, mirrors Skill.name
provider         CharField, blank=True
description      TextField, blank=True
hours            DecimalField(6,1), null, blank — same shape as TrainingRecord.hours
mandatory        BooleanField, default=False — catalogue metadata (§2.2)
validity_days    PositiveIntegerField, null, blank — renewal cycle (e.g. 365 for an annual refresher);
                 None = does not expire once completed
active           BooleanField, default=True — mirrors Skill.active
```

### 4.2 `learning.CourseRequirement`

```
course               FK Course, PROTECT, related_name="requirements" — mirrors EmployeeSkill.skill (PROTECT:
                     a catalogue entry with an active rule against it can't be silently deleted out from under it)
department            FK core_hr.Department, PROTECT, null, blank
occupational_level     FK core_hr.OccupationalLevel, PROTECT, null, blank
effective_from          DateField — when this rule starts applying (can be in the future or the past;
                        §2.4 — a rule added today can predate or postdate any given employee's tenure)
due_within_days           PositiveIntegerField — grace period from "became subject to this rule" to due
active                     BooleanField, default=True — retire a rule without deleting it (nothing is stored
                          against it to cascade, since compliance is derived, so "delete" would be equally
                          safe, but `active` matches every other catalogue-adjacent model's own convention
                          — Skill, Course itself — and preserves the rule's own history for audit purposes)
```
No hard DB uniqueness constraint on `(course, department, occupational_level)` — `NULL` is not equal to itself
under standard SQL uniqueness semantics, so a `UniqueConstraint` would not actually prevent two organisation-
wide (`department=None, occupational_level=None`) rules for the same course, the exact case most likely to be
duplicated by mistake. Instead, `CourseRequirementSerializer.validate()` explicitly checks for an existing
*active* rule with the identical `(course, department, occupational_level)` triple (treating `None` as equal
to `None`, unlike the DB-level constraint) and rejects a duplicate — application-level validation chosen
specifically because it covers the case the DB constraint cannot.

### 4.3 `learning.TrainingRecord` (extended)

```
course          FK Course, SET_NULL, null, blank, related_name="training_records" — new; nullable per §2.5
```
`SET_NULL` (not `PROTECT`) — deleting a `Course` from the catalogue should not be blocked by, or cascade into
deleting, historical training records; it just detaches them back to free-text-only, the same state records
created before the catalogue existed are already in.

---

## 5. Access control

### 5.1 `Course` / `CourseRequirement`

Same shape as `Skill`: `IsHRAdminOrReadOnly` on both. Public tier (no `FIELD_TIERS` entry needed, matching
`Skill`/`skills_inventory`'s own reasoning: "the catalog itself isn't sensitive") — any authenticated employee
can read the catalogue and the requirement rules (needed for dropdowns, and for a manager to understand *why*
someone shows up on their overdue list); only `hr_admin` manages either.

### 5.2 `TrainingRecord.course`

No new access-control surface — it's one more field on a model whose write/read rules (self, own_team via
manager, `hr_admin`; Sprint-15 self-submission stripping) are entirely unchanged (§2.5, §6 guardrail).
`FIELD_TIERS["learning.TrainingRecord"]` gains a `"course": FieldTier.INTERNAL` entry, matching `title`/
`provider`'s existing tier on the same model — consistent, not a new judgement call.

### 5.3 Completion-rate dashboard (aggregate, by course / department / occupational level)

**`hr_admin` only** (`IsHRAdmin`), identical gate to `skills_inventory` — same precedent, same reasoning: an
org-wide statistical rollup with no per-employee names in it is HR/compliance-reporting territory, not
something every manager needs a dedicated aggregate view for (a manager gets their own team's detail via
§5.4, not the org-wide rates). No small-cell suppression is applied to the aggregate — like
`skills_inventory`'s own explicit reasoning ("skill possession is Internal-tier, not Sensitive... that rule
targets demographic aggregates specifically"), training completion is Internal-tier subject matter and this
endpoint is already `hr_admin`-only, so the suppression mechanism (which exists to protect a *broader*
audience than hr_admin from re-identifying someone inside a small demographic cell) has no audience to protect
against here.

### 5.4 Overdue-individuals list — row-scoped, not org-wide-by-default

This is named data (who, which course, how overdue) and the brief explicitly flags it needs a scoping
decision, not an unscoped org-wide list. Decision: reuse `rbac_audit.drf.row_scoped_queryset` exactly the way
`learning/views.py::team_development` already does (`row_scoped_queryset(Employee.objects.all(), employee,
employee_field=None)`) — **no new privacy mechanism was invented for this.** Concretely: `hr_admin`/`auditor`/
other `row_scope=all` roles see everyone's overdue status org-wide; `line_manager` sees only employees in
their reporting chain (`own_team`); a base `employee`-only role sees only themselves. This is exactly the
"line manager should only see their own reports' overdue status, not the whole org" outcome the brief asks
for, achieved by reusing existing, already-audited infrastructure rather than building bespoke row-scoping
for this one endpoint. `permission_classes = [permissions.IsAuthenticated]`, same as `team_development`.

Small-cell suppression was considered and set aside for this endpoint specifically (unlike the aggregate
dashboard, this list *does* name individuals): suppression exists to protect *demographic* aggregates from
re-identification by a wide audience holding only aggregate-level grants (RBAC-Roles.md standing rule 1). This
list is not a demographic aggregate — it's already row-scoped to exactly the people the requester has a
legitimate operational reason to see individually (their own reports, or everyone if they hold an all-scope
HR role), the identical exposure `team_development`'s skill/certification/training *counts* already carry per
employee. Suppression would be solving a problem this endpoint's access control doesn't have.

---

## 6. Compliance derivation (`learning/compliance.py`)

Given an `as_of` date (defaults to today) and a queryset of employees:

1. Load every **active** `CourseRequirement` whose `effective_from <= as_of` and whose `course.active` is
   True, `select_related("course", "department", "occupational_level")`.
2. For each employee, resolve `current_version` (skip if `None` — already flagged separately by
   `core_hr.data_quality`'s `ORPHAN_RECORD` check; not this module's concern to re-flag). A requirement
   *applies* if its `department` is null or matches the version's, **and** its `occupational_level` is null or
   matches the version's (both-null requirements apply to everyone).
3. `subject_since = max(requirement.effective_from, version.valid_from)` — the later of "the rule existed" and
   "this employee has been in the version currently on record" (so a rule added after someone was already
   employed starts their clock at the rule's own start date, per the brief's explicit requirement; someone who
   transfers into a newly-scoped department starts their clock at the transfer date via `valid_from` on their
   new version, not their original hire date).
4. Look up the most recent `TrainingRecord(employee=X, course=requirement.course, status=COMPLETED,
   completion_date__isnull=False)` — one batched query per call across all employees/courses in scope
   (`values("employee_id", "course_id").annotate(latest=Max("completion_date"))`), not one query per employee
   (the guardrail against N+1 on exactly this kind of aggregating endpoint).
5. Status:
   - No qualifying completion at all → compare `as_of` to `subject_since + due_within_days`: **due** if not
     yet reached, **overdue** if passed.
   - A qualifying completion exists and `course.validity_days` is `None` → **compliant**, permanently (nothing
     to renew).
   - A qualifying completion exists and `course.validity_days` is set → compare `as_of` to
     `latest_completion_date + validity_days`: **compliant** if not yet reached, **overdue** (renewal lapsed)
     if passed — the renewal due date, not `subject_since`, becomes the relevant date once someone has
     completed it at least once.

`compliance_for_employee(employee, as_of=None)` (single-employee form, for the manager-view row detail) and
`compliance_matrix(employees_qs, as_of=None)` (aggregate rollup, for §5.3) share this same core loop —
implemented once, not duplicated, mirroring `skills_inventory`/`team_development`'s own each-doing-their-own-
aggregation-once shape.

---

## 7. Testing

Mirrors `learning/tests.py` (service-layer, direct model tests — every branch of §6's status derivation:
not-yet-subject via future `effective_from`, due-not-yet-overdue, overdue via no completion, compliant with no
expiry, compliant-then-expired-renewal, department-only scope, occupational-level-only scope, both-null
org-wide scope, department+level intersection) and `learning/test_api.py`'s shape (role-matrix assertions:
catalogue read-open/write-hr_admin-only; requirement validation rejects a non-mandatory course and a duplicate
active scope; the aggregate dashboard is hr_admin-only; the overdue list is row-scoped exactly like
`team_development` — manager sees only their report, not the outsider; self-submission via ESS is unaffected
by the new `course` field). `learning/test_data_quality.py` for the registered handler (mirrors `performance/
test_data_quality.py`'s shape: register, run `run_data_quality_checks()`, assert the exception opens/
auto-resolves). A `learning/test_reminders.py` for the Celery task's offset/escalation logic, mirroring
`core_hr/test_reminders.py`.

---

## 8. Known boundaries

- **No automatic enrollment.** A `CourseRequirement` makes someone *subject* to a course; nothing creates a
  `TrainingRecord(status=PLANNED)` on their behalf when a new rule takes effect or when they transfer into
  scope. HR/the employee still create the enrolment through the existing flow, same as skills/certifications
  today. Flagged as real, deliberately out of scope — the brief's own "no automatic enrollment" boundary.
- **No SETA-levy cost rollup.** `Course.hours`/`TrainingRecord.cost` exist, but nothing aggregates spend
  against the Skills Development Levy the way a real SETA/skills-levy tracking feature (also named in
  `NEXT_AGENT_BRIEF.md` §7.3 #21 alongside this) would. This slice builds the catalogue + compliance half of
  #21, not the levy-tracking half — a materially separate piece of work (levy-eligible-spend rules,
  SDL-specific reporting) that was not part of what the brief scoped as "what to build" for this session.
- **Historical free-text `TrainingRecord.title` rows never retroactively satisfy a requirement** (§2.5) — by
  design, not a gap, since no reliable title→course mapping exists to backfill safely.
- **`wsp_atr_export` unchanged** (§2.6) — confirmed correct on inspection of the actual query, not left
  unexamined.
- **Reminder task accepts same-day-rerun double-send risk**, identical posture to `contract_reminders.py`
  (§2.9) — an extra nudge, not a duplicate decision or data change.
