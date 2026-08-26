# EE Plan Depth + Consultation-Forum Records — Design Spec

C6, last effort-buildable sub-item (`docs/sprints/backlog-uat1-and-c2-c7.md`: "EE plan + consultation-forum
records"). `NEXT_AGENT_BRIEF.md` §7.3 #23: *"EE plan (EEA13-style targets/barriers plan) + consultation-forum
records + monitoring of numerical goals — `EEPlan` exists as a model; the committee/consultation evidence trail
(which the EEA2 questionnaire asks about) is not captured anywhere."* The remaining C6 item after this (real
assessment-provider adapter) stays vendor-blocked (Sprint-0 action A4).

## References

- Employment Equity Act 55 of 1998: s.16 (consultation — representative trade unions and employees/nominated
  representatives, reflecting *all occupational levels*, *designated and non-designated groups*), s.17 (matters
  for consultation: the analysis, the plan, the report), s.19–20 (analysis; plan contents — barriers,
  affirmative-action measures, numerical goals, timetable, monitoring), s.24 (assigned senior manager), s.43
  (DG review — the "show me the evidence" path).
- 2025 EE Regulations + sectoral numerical targets, in force: 18 sectors, targets set per **occupational
  level (top four)** per designated group, plus a **workforce-wide 3% disability target**; plan period
  **1 Sep 2025 – 31 Aug 2030**. `EEPlan.sector_targets` / `numerical_goals` / `disability_5yr_target_pct`
  already carry this shape (level × demographic column %, disability as a single %), so the snapshot below
  compares against it without a schema change.
- **Draft Amended Code of Good Practice on the Preparation and Implementation of the EE Plan**, published for
  public comment 31 July 2026 — referenced, not implemented against: the coordinator is running a separate
  regulatory piece. Nothing here hard-codes a Code-specific rule beyond what the Act and the EEA2 form already
  require; the model is deliberately shaped so per-level/per-group targets and a disability target are what
  gets monitored.
- `EEA-Form-Spec-Notes.md`, `EEA2 Form.docx` (Section F: consultation Y/N × 3 stakeholders; barriers/AA
  measures Y/N × 24 categories).
- Precedents reused: `2026-08-26-salary-review-cycles-total-rewards-design.md` (services under
  `transaction.atomic`, data-quality registration), `2026-08-25-succession-talent-pools-design.md` (access
  control shape), `performance.EvidenceItem` + `documents/validation.py` (content-sniffed uploads,
  authenticated `FileResponse` download), `core_hr/data_quality.py` registry.

---

## 1. The problem

`EEQuestionnaire.consultation["consultative_body_or_ee_forum"]` and each `barriers[<category>]` entry are bare
Y/N answers that the Accounting Officer signs. Nothing behind them exists in the system: no record of who sits on
the EE committee, when it met, what it resolved, what the plan's barriers/measures actually are (owner, dates,
status), or how the numerical goals have tracked over the plan period rather than "today vs target". A DEL
inspection or a s.43 DG review asks for exactly that evidence.

## 2. Where it lives: `ee_reporting`

Squarely this app's domain — every model here exists to evidence what `EEQuestionnaire`/`EEReport` declare, and
the validation pass that cross-checks them (`validation.py`) is here. A separate app would force the
questionnaire cross-check through a `queries.py` seam for no boundary benefit. `ee_reporting` stays an ordinary
domain app; nothing new needs a reverse FK into it.

## 3. Consultation forum / EE committee (A)

### 3.1 `EEForumMember`

| field | notes |
|---|---|
| `employee` FK | the person |
| `representation` | `union_nominated` / `employee_nominated` / `employer` — the s.16(1) consulting parties (union(s); employees or their nominated representatives) plus the employer side (the s.24 assigned senior manager and management nominees). Designated-group and occupational-level coverage are **not** stored — they are properties of the employee's current `EmployeeVersion` (race/gender/disability, occupational level) and are derived at check time (§3.3), so a member's promotion or a demographic correction never leaves a stale copy here. |
| `role` | `chair` / `secretary` / `member` |
| `term_start`, `term_end` (nullable) | active = `term_start <= today` and (`term_end` null or `>= today`) |
| `notes` | free text (e.g. which union) |

No uniqueness on `employee` — a person can serve two non-overlapping terms; overlapping active terms for the
same employee are rejected in the serializer.

### 3.2 `EEForumMeeting`

`meeting_date`, `title`, `report_year` (int — the EEA2 year this meeting evidences; **not** an FK to
`EEQuestionnaire`, which frequently doesn't exist yet when the first meeting of the year is minuted — it is
matched by value against `EEQuestionnaire.report_year`, the questionnaire's own unique key), `agenda`,
`summary`, `resolutions` (text), `attendees` M2M → `EEForumMember` (so quorum/attendance is factual, not a
count typed in), `minutes_file` (nullable), `minutes_content_type`, `minutes_sha256`, `recorded_by`.

Minutes upload: content-sniffed PDF or DOCX only, 10 MB cap. `documents/validation.py` is the reference
implementation but `documents` is a peer domain app, not kernel, so it cannot be imported; the sniff is
reimplemented in `ee_reporting/uploads.py` (a lift of the shared sniffer into `rbac_audit` or `core_hr` is a
noted follow-up, not done here — three copies would justify it; two don't yet). Download is an authenticated
viewset action returning `FileResponse`, `log_access`'d as `EXPORT` at `FieldTier.SENSITIVE` (the minutes discuss
demographic composition), never a raw `MEDIA_URL`.

### 3.3 Composition adequacy — derived, not stored

`GET /ee-forum-members/composition/` computes, from the active members' current `EmployeeVersion`s, against the
current workforce (`EmployeeVersion.objects.as_at(today)`):

- which occupational levels present in the workforce have no active member (s.16(2)(a));
- whether designated-group and non-designated-group employees are both represented (s.16(2)(b)); "designated"
  here = Black (African/Coloured/Indian) or female or has a disability, per the Act's definition, from the
  same fields `aggregation.py` uses;
- whether any `union_nominated` member is active (informational — the system doesn't know whether a
  representative union exists);
- per-representation counts.

Counts of members by demographic group are **not** returned (the forum is ~5–15 people; every cell is a small
cell). The check returns booleans and level codes only, which is what the adequacy question needs.

### 3.4 Questionnaire link — validate, don't derive

**Decision: the manual Y/N stays authoritative; `validation.py` gains findings.** Rejected deriving the answer
(Y iff ≥1 meeting in the year, with an override+reason): (a) the questionnaire is frozen into `EEReport.data`
by `_serialize_questionnaire` at generation — a derived answer changes report-generation semantics and every
existing test around it; (b) Section F is the employer's *declaration*, signed by the Accounting Officer; the
system's job is to evidence it, not to answer it for them; (c) an override field is a second stored state whose
reason text nobody validates. The validation route is lower-risk to generation/export and matches how
`_barrier_grid_completeness_issues` already treats Section F — advisory findings on the `validate` action, which
a reviewer decides on before sign-off.

New advisory findings in `validate_report_data` (EEA2 only), all read the *frozen* questionnaire in
`report.data` and live forum/plan records:

1. `consultative_body_or_ee_forum` is `True` and no `EEForumMeeting` with `report_year == report.report_year`
   exists → *"Section F claims consultation with the EE forum, but no forum meeting is on record for
   {year}."*
2. `consultative_body_or_ee_forum` is `False`/absent and ≥1 meeting exists for the year → the converse, so a
   stale "No" gets caught too.
3. For each of the 24 categories: `aa_measures` is `True` but the plan covering `report.period_end` has no
   `EEPlanMeasure` in that category → *"'{label}': AA measures claimed, no measure on the EE plan."* And the
   converse (a measure exists, grid says `False`).
4. `barriers` is `True` but no measure with a non-blank `barrier_description` in that category — folded into 3
   (a measure row carries both halves).

`validate_report_readiness` (the generation *gate*) is **not** touched — a missing forum record must never block
generating a draft; that is exactly the kind of thing a draft is for surfacing.

## 4. EE plan depth + monitoring (B)

### 4.1 `EEPlanMeasure`

`plan` FK → `EEPlan`, `category` (choices = `BARRIER_CATEGORIES` keys, count untouched), `barrier_description`,
`measure_description`, `owner` FK Employee (nullable, SET_NULL), `target_start`, `target_end`, `status`
(`planned` / `in_progress` / `completed` / `abandoned`), `progress_notes`, `history`. Several measures per
category are allowed (one barrier can have several remedies). Same validate-don't-derive shape as §3.4 for the
barriers grid, for consistency.

### 4.2 `EEPlanProgressSnapshot` — the one place storing beats deriving

`plan` FK, `as_of` date (unique per plan), `workforce_profile` + `disability_workforce` (the full,
**unsuppressed** 10-column matrices from `aggregation.py`, exactly what `EEReport` freezes), `annual_target_gap_pct`
(`dashboards._target_gap` against `plan.annual_targets`), `sector_target_gap_pct` (same function against
`sector_targets` merged with `numerical_goals` — the 5-year 2025 sector-target shape, level × group), `disability_pct`
(workforce-wide, vs `disability_5yr_target_pct`), `taken_by`, `note`. Create-only; no update/delete endpoints.

Why store: `EmployeeVersion.as_at()` can recompute a matrix for a past date *today*, but (a) versions are
corrected retroactively (that is what versioned history is for) and are subject to `rbac_audit` retention/
anonymisation, so a recomputation five years into a plan period is neither cheap nor guaranteed to reproduce
what the forum actually saw; (b) the snapshot is *evidence* — "at the Q3 meeting we tabled these figures" —
the same reason `EEReport.data` is frozen rather than re-aggregated on read (Architecture-Design §5.1). The
live equity dashboard remains derived; snapshots are the trend.

Small-cell suppression: `GET` applies `dashboards._suppress_matrix` per requester
(`can_see_unsuppressed_aggregates(employee, FieldTier.SENSITIVE)`), identical to the live dashboard. The raw
stored matrix is never returned to a role that would see the live one suppressed.

### 4.3 Data-quality check

`DataQualityException.ExceptionType.EE_MEASURE_OVERDUE` (registered from `EeReportingConfig.ready()`): a
`planned`/`in_progress` measure past `target_end`, attached to the measure's `owner` (skipped when ownerless —
the registry's contract needs an employee; the measures section shows the same overdue flag regardless).
Composition adequacy is *not* a DQ entry: it has no employee to hang on and is already surfaced live on the
forum page.

## 5. Access control (C)

| Surface | Read | Write |
|---|---|---|
| forum members, meetings, minutes download, composition | hr_admin, ee_manager, accounting_officer, auditor; **plus a forum member for the member list and the meetings they attended** | hr_admin, ee_manager |
| plan measures | EE read roles | hr_admin, ee_manager |
| progress snapshots | EE read roles | hr_admin, ee_manager (create only) |

**ee_manager writes** — a deliberate departure from the existing `_require_hr_admin` on config/plan/
questionnaire writes. Those are the statutory *form data* hr_admin transcribes; the forum, the measures and
the monitoring are the EE manager's own operational job (RBAC-Roles.md gives ee_manager RW on the Sensitive
tier and "EE reporting"; the Act's s.24 senior manager runs consultation). The `EEPlan` row itself stays
hr_admin-write. `accounting_officer`/`auditor` read-only, as everywhere in the module.

**Forum-member carve-out** — granted, minimally. A nominated representative cannot represent employees at a
meeting whose minutes they cannot see; s.16 consultation presupposes that the parties hold the record. Scope:
the member list (names/roles/terms — who they sit with) and meetings where they are an attendee, including
minutes download. Not: meetings they did not attend, the composition check, plan measures, snapshots, or
anything on `/ee-configuration`. Implemented as a queryset filter on the two forum viewsets
(`EEForumPermission`: any authenticated employee reaches `GET`; the queryset narrows to own-membership /
self-attended for non-EE roles; writes stay role-gated). An employee who is not a member sees an empty list,
not a 403 — no hint about what exists. There is no member-facing page in this slice; the `/ee-forum` route and
nav item are gated to EE roles, and the carve-out is API-level (a "my forum" page is a follow-up if asked for).

## 6. API

Router: `ee-forum-members` (CRUD, `?active=1`, `composition/` list-action), `ee-forum-meetings` (CRUD,
`?report_year=`, multipart create/patch for `minutes_file`, `download_minutes/` detail action),
`ee-plan-measures` (CRUD, `?plan=`, `?category=`, `?status=`), `ee-plan-snapshots` (list/retrieve/create,
`?plan=`; create body `{plan, as_of?, note?}` — the matrices are always server-computed, never client-writable).
All list endpoints `select_related`/`prefetch_related` the FKs they serialize.

## 7. Frontend

New `EEForumPage.tsx` (`/ee-forum`, EE roles): members table + add/end-term form, composition panel (levels
uncovered, designated/non-designated flags, union-nominated present), meetings list with attendee ticks, minutes
upload (multipart) and authenticated download link. `EEConfigurationPage.tsx` gains two sections under the
existing questionnaire: **Plan measures** (per-category rows with owner/status/dates, add/edit for writers) and
**Progress snapshots** (take-snapshot button for writers; a trend table of `disability_pct` and per-level gap
per snapshot, suppression-aware). Nav: `Equity` → `EE Forum`. Write controls hidden for
accounting_officer/auditor (server enforces).

## 8. Seed

One forum (chair = ee_manager demo login as `employer`, four `employee_nominated` members across levels, one
`union_nominated`), two 2026 meetings (attendance differing, one with a generated PDF minutes file), six
measures on the 2025–2030 plan matching the six barrier categories the seeded questionnaire already answers
`True` (so the seeded signed-off EEA2 validates clean), two snapshots (one back-dated to plan start, one today).

## 9. Out of scope / recorded gaps

Meeting scheduling/invites/quorum rules (a quorum is a forum's own constitution, not statute); a member-facing
"my forum" page; lifting the upload sniffer into the kernel; EEA13 document export (the plan-document render
itself — the measures/targets are the data, the form render is a C7 report-builder concern); an automatic
snapshot schedule (on-demand + `monitoring_frequency` is enough until a scheduler exists).
