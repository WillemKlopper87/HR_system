# Investigation: Performance / KPI Contracting Workflow (Performance Agreements)

**Date:** 2026-08-18 · **Status:** investigation only — nothing built, no ADR yet · **Requested by:** user
**Purpose:** answer "can the HCM manage the KPI-contracting process end-to-end?" — periods, templates, evidence
storage/archiving, signing — against what already exists, and propose how it would be built. To be refined against
Sentech's internal PMDS process before any spec is written.

> **Assumption on "PFM":** read as *Performance Management* — i.e. the current `performance` module plus the generic
> public-sector Performance Management & Development System (PMDS) framework used as the reference structure. If "PFM"
> refers to a specific internal document (a PFM policy / performance-agreement template), share it and §3–§5 get
> re-cut against it.

---

## 1. What exists today (`hcm/backend/performance/`, 134 lines of models)

| Model | What it is | Gap vs. KPI contracting |
|---|---|---|
| `ReviewCycle` | name, `annual`/`biannual`, start/end date, `draft→launched→closed` | Has no *phases* (contracting window, mid-year, final assessment, moderation), no per-phase open/close dates |
| `Review` | one row per employee per cycle; **single** overall self-rating + manager-rating (1–5) + comments; manager snapshotted at launch | No KPA/KPI rows, no weights, no target/measure, no scoring, no moderation, no signature |
| `Goal` | free-standing goal per employee (title, description, target date, status) | Not linked to a cycle or a contract; no weight; not signed |
| `Feedback` | manager/peer text feedback | Fine as-is; orthogonal |

Access model already in place and reusable: `line_manager` sees own team's reviews/goals via `RowScopePermission`;
`hr_admin` sees all; ratings are treated as Sensitive but gated by row-scope rather than field tiers (documented in
the model docstring). Frontend: `ReviewCyclesPage`, `ReviewsPage`, `ReviewDetailPage`, Goals/Feedback sections on
`EmployeeDetailPage`.

**Reusable building blocks elsewhere in the codebase (this is what makes the feature cheap-ish):**
- File storage + authenticated download: `policies.Policy.source_file` + `PolicyViewSet.download` (`FileResponse`,
  permission-checked) — the pattern for portfolio-of-evidence files.
- Versioned documents + acknowledgment: `policies` (publish/archive/new-version, `PolicyAcknowledgment`) — the shape
  for versioned templates and for "employee acknowledged/signed at time T".
- Step-up MFA (ADR-009, `rbac_audit/stepup.py`): TOTP + reason → time-boxed grant, audit-logged — a ready-made
  "prove it's you" step for a signature act.
- Audit log (`AuditLogEntry`), `simple-history` (`HistoricalRecords`) for amendment history.
- PDF generation (`reportlab`, used by EE reports) — for the signed-agreement snapshot.
- `JobGrade` / `OccupationalLevel` / `Department` — targeting keys for templates.
- Consent (`ConsentRecord`) — probably not needed here (performance data isn't special-category), noted for completeness.

**Absent (would need to be added, see NEXT_AGENT_BRIEF §7):** notifications/email (contracting deadlines, sign
requests), Celery (PDF generation/archiving in background), delegation (acting manager signs).

## 2. Reference structure — how KPI contracting normally works (SA public-sector / SOE PMDS)

The generic lifecycle almost every SOE/department follows; Sentech's version will differ in details (§6):

```
Corporate scorecard / shareholder compact
   └─ Divisional / departmental scorecard (cascade)
        └─ Individual Performance Agreement (per employee, per performance period)
             ├─ Key Performance Areas (KPAs) — weighted, weights sum to 100 %
             │    └─ KPIs / measures — target, evidence required, due date, (weight within KPA)
             ├─ Generic Assessment Factors / competencies (GAFs) — often an 80/20 or 70/30 KPA:GAF split
             ├─ Personal Development Plan (PDP) — links to learning module
             └─ Signatures: employee + supervisor (+ HR/next-level manager as witness), dated
```

**Period phases (typically the financial year, Apr–Mar for SOEs):**

| Phase | Window | Output | Signed by |
|---|---|---|---|
| Contracting | first N weeks of period | Agreement `agreed` | employee, supervisor |
| Quarterly / mid-year review | Q2 (and Q1/Q3 optional) | interim ratings + evidence, possible **amendment** (re-contract) | both, on the review record |
| Annual assessment | after period end | self-assessment → supervisor assessment, per element | both |
| Moderation | committee | moderated final score, may override with reason | chair / hr_admin |
| Outcome | after moderation | final rating → incentive / PDP / improvement plan; agreement **archived** | — |

**Scoring:** per element rating on a 5-point scale × weight → weighted score; GAF score blended; final band
(e.g. <3 = below, 3 = fully effective, 4–5 = above) drives pay/bonus (link to `compensation.CompProposal`).

**Portfolio of Evidence (PoE):** files attached *per KPI/element* (and per review stage), reviewed by the supervisor;
retained with the agreement for audit; the whole signed agreement + assessment is exported to a PDF snapshot and
archived per period.

**Signing:** SA's ECT Act recognises ordinary electronic signatures (click-to-sign with identity assurance + audit
trail) as valid unless a law demands an *advanced* signature; performance agreements do not. So an in-app
signature that captures who/when/what-hash, backed by re-authentication, is sufficient — a DocuSign-style vendor is
optional, not required.

## 2a. What the actual Sentech scorecard template says (extracted 2026-08-18)

Source: two filled-in *Individual Scorecard* workbooks in the repo root (`Scorecard_2026_27_…xlsx`,
`…Scorecard_2025_26_…xlsx`). Only the **structure** is recorded here — they contain one person's real ratings and
comments. **Do not commit them as-is** (`.gitignore` them or replace with a blanked copy) — they are personal data
under POPIA and the repo is on GitHub.

**Layout (one sheet per FY + a `PDP` sheet):**

```
Title:  "Individual Scorecard for <Job title> <FY> Financial Year"      (FY = April–March)
Header: Name and Surname · Division · Job Title · Date
        Signed Manager (Head – <division>) · Signed Individual (<job title>)
        [2025/26 also: "Final Score", "Rev3"/"Rev4" revision counters]

Grid (one row per KPI):
  OBJECTIVE / PERSPECTIVE │ KPA Description │ Key Performance Indicator │ Metric │ Weight │ 1 │ 2 │ 3 │ 4 │ 5
                                                                                            └── "Target Setting wrt Expectation":
                                                                                                per-KPI text for each level:
                                                                                                1 Below Target · 2 Partially meets target ·
                                                                                                3 On Target · 4 Stretch Target · 5 Exceeded Stretch Target
  … SUB-TOTAL row per objective (Σ weights) … grand total row (must be 1.00)

Review columns (2025/26): "Performance Review: Q2" → Q2 Target · Employee Comments · Manager Comments
                          "Review: Q4"             → Actual Rating (1–5) · Score (= weight × rating) · Employee Comments
                          Final Score = Σ Score
PDP sheet: Business process │ Courses/Training/Certificate  … NAME (EMPLOYEE) · SIGNATURE · DATE
```

**Facts this settles (maps to §6):**

| §6 Q | Answer from the template |
|---|---|
| 2 Period | **Confirmed by user 2026-08-18: financial year runs 1 April (current year) → 31 March (following year)** — so a `PerformancePeriod` is named by FY (e.g. "2026/27"), `start_date=1 Apr`, `end_date=31 Mar`, and the system should default-create the next FY period from that rule; contracting at period start (April, signed ~June); **Q2 mid-year review** (target check + both parties' comments) and **Q4 final review** (rating + score). Two review points, not quarterly. |
| 3 Structure | Three-level: **Objective/Perspective → KPA → KPI**. Weight sits on the **KPI** (decimal, sub-total per objective, total 1.00). Rating scale **1–5** with fixed labels; the target for *each* level is written per KPI ("On Target = R1m; Stretch = R1.5m"). Metric is free text (ZAR, #, %, Deadline, Qualitative/Quantitative, Feasibility/Pilot). **No GAF/competency block.** Score = weight × rating; final = Σ. |
| 3 Cascade | The top-level grouping is the **corporate strategy**: 2025/26 used Balanced-Scorecard perspectives (Financial / Customer / Internal Processes / Learning & Growth); 2026/27 uses the corporate strategic objectives (Drive Sustainable Growth / Deliver Reliable Customer-Centric Services / Build Future-Ready and Trusted Organisation). → objectives are a **locked, template-owned list per FY**; KPAs/KPIs are individual. |
| 4 Signers | **Two**: the individual and the manager (Head of division / executive). No HR witness on the form. The PDP is signed by the employee separately. **User 2026-08-18:** the document is reviewed together first; when both are happy the **staff member signs first, then the Head/executive** (strict order); the signed document is then **shared with HR** — HR is a *recipient/archive*, not a signatory. Day-to-day interaction is local (staff ↔ Head); **HR only gets involved when there is a performance issue** (KPIs not met) — they investigate why (capability/support vs. wilful) and *may* put an improvement plan in place (structure unknown to the user). |
| 5 Amendments | "Rev3/Rev4" counters (with broken `#REF!` formulas) show revisions happen and are tracked by hand → versioned agreement with amendment history is needed. |
| 3 Overall score (user, 2026-08-18) | **Final score is on the same 1–5 scale**: Σ(weight × KPI rating) with weights summing to 1.00, so the total is bounded 1–5 by construction. **3 = doing your job (fully effective), 5 = exceptional.** Suggested bands to confirm against the policy: <2 unsatisfactory · 2–<3 partially effective · 3–<4 fully effective · 4–<5 exceeds · 5 exceptional (only the 3 and 5 anchors are user-confirmed). Validation rule for the system: weights must sum to exactly 1.00 before an agreement can be submitted for signature. |
| 9 Outcome | PDP is part of the same document → link agreement → `learning` (training requests). |
| 10 Templates | The template changed shape between FYs → templates must be **versioned per period**, and an agreement snapshots the version it was created from. |

**Still open after the template:** moderation step (none mentioned so far — assume none until told otherwise); signature strength (click-to-sign vs MFA); is a "Q2 rating" ever captured or only
comments; whether the same form applies to all levels (SMS/executive vs staff) or there are variants; retention.

**Workflow this settles:** `draft` (either party edits, comments) → `submitted` by employee → Head reviews (`returned` with
comments, or approves) → **`employee_signed`** → **`head_signed` = agreed** → HR receives it automatically (visible in
hr_admin's list + archived PDF; a notification to HR is a nice-to-have, not a gate). Same order for Q2/Q4 stages and
amendments. Signature is only ever offered in that order — the Head's "sign" button is disabled until the employee has
signed. **Underperformance path:** a final (or Q2 flagged) rating **< 3** on the overall score — or on any KPI, to be
confirmed — raises an *HR attention* flag on the agreement (visible to hr_admin, notification later); an optional
`ImprovementPlan` record (owner, reasons, actions, review dates, outcome) is the natural PC-3 add-on but its real
structure is unknown — do not design it beyond a stub until HR describes it. This is also the hook into the
labour-relations gap in NEXT_AGENT_BRIEF §7.3.

**Evidence (user 2026-08-18):** today the portfolio of evidence lives **on each person's PC**; OneDrive/Teams is
available but there is no formal process. The desired state is that evidence is **available in the system per KPI,
per review**, backing the quarter's comments (the comment is the employee's short narrative for the score; evidence
substantiates it) so the Head can judge whether the rating is low/right/high. Design consequence:
- `EvidenceItem` hangs off **element × review stage** (Q2 / Q4), with `kind = file | link` — uploaded file (policies
  pattern, authenticated download, hashed) **or** a OneDrive/Teams/SharePoint URL, since that's where people already
  keep things (a Graph-API picker is a later nicety, not needed for v1).
- Not a hard gate by default: a rating can be entered without evidence, but the Head's review view shows an explicit
  **"no evidence attached"** marker per KPI, and the template carries `evidence_required: bool` so HR can flip it to
  mandatory later (or per objective) once the habit exists. Recommend starting *optional-but-visible*, not blocking.
- Comments per KPI per stage stay exactly as on the form (employee comment, manager comment); evidence attaches to the
  same row. Evidence uploaded after signing of that stage is allowed but stamped "added after sign-off" (audit).
- Retention: evidence follows the agreement's archive/retention rule; never hard-deleted after sign-off.

**Primary driver (user 2026-08-18) — schedule + reminders, less paperwork:** the pain is not the form, it's that
KPIs are forgotten until a last-minute rush; corporate reminder emails exist but are ad hoc. Staff are overloaded,
and from an HR/policy view that is not an excuse — so the system must **push and remind in advance**, in a
structured, scheduled way, with the collab platform as the delivery surface. Design consequence — a **reminder
schedule is a first-class part of the period, not a later nicety**:
- `PerformancePeriod` phases (contracting / Q2 / Q4 / archive) each get open+close dates **and reminder offsets**
  (e.g. T-28d "start preparing", T-14d, T-7d, T-1d, overdue daily/weekly), editable by hr_admin per period, defaulted
  from the previous period.
- Each reminder becomes: a collab **work item** per employee per phase (created at T-28d, priority raised as the
  deadline nears, closed automatically when the stage is signed), a **critical announcement/popup** at phase open and
  at overdue, and (once email exists) an email — all generated by one scheduler job (Celery beat), idempotent via
  `external_ref`, so nothing is sent twice and nothing is sent to someone who has already completed the step.
- Reminders are **targeted by state**: only people whose agreement is not yet at the required stage get them; Heads get
  a separate "N of your team still outstanding" digest; hr_admin sees the completion dashboard by division.
- Deep link in every reminder to the exact step in the HR SPA (`/my-performance/…`), so "preparing" means opening the
  scorecard, not hunting for a spreadsheet.
- Delegation/acting-Head signing (user 2026-08-18): normally the Head signs **before going on leave**; otherwise **a
  person designated by the boss has authority** to sign in their place. → a small, explicit `SigningDelegation`
  (delegator = the Head, delegate = another employee, date range, scope = performance signing; created by the Head
  themself or by hr_admin; audit-logged) is in scope for PC-1. During the range the delegate sees the Head's
  outstanding sign-offs and the signature record reads "signed by <delegate> acting for <Head>" — the delegator is
  never shown as the signer. Reminders to the Head are mirrored to the active delegate. Matrix/project reporting is
  still not modelled — the org-chart line manager remains the contracting Head.

**Model refinements this forces (applied to §3):** `TemplateElement`/`AgreementElement` get `metric` and a
`level_descriptors` JSON `{1:…,5:…}` instead of a single `target`; a **section** concept (Objective/Perspective) with
weight sub-totals; review stages are exactly `midyear` (Q2: target note + comments) and `final` (Q4: rating + score +
comments); `AgreementScore = Σ(weight × final_rating)`; a `PDPItem` list attached to the agreement, signable, feeding
`learning.TrainingRecord(REQUESTED)`; the generated PDF should reproduce this exact grid so it is recognisable to
staff who know the spreadsheet.

## 3. Proposed domain model (builds on, not beside, the existing module)

```
ReviewCycle  ──(rename/alias: PerformancePeriod)──  gains phases:
   contracting_open/close, midyear_open/close, final_open/close, moderation_open/close
   status: draft → contracting → active → midyear → assessment → moderation → closed → archived

AgreementTemplate            versioned (like Policy): name, version, status draft/published/retired,
  ├─ targeting: job grades / occupational levels / departments (any-of), effective period(s)
  ├─ rating_scale (JSON: 1–5 with labels), kpa_weight_pct / gaf_weight_pct
  ├─ signatory rules (who must sign, order, whether HR witness required)
  ├─ evidence rules (required per element? allowed file types, max size)
  ├─ TemplateSection[]: the Objective/Perspective list for that FY (locked, ordered) — sub-total of weights per section
  └─ TemplateElement[]: section, kpa_description, kpi_title, metric, default weight, level_descriptors JSON {1..5},
                        order, locked (cascaded) or editable; kind KPI (GAF kept as an option, not used by Sentech's form)

PerformanceAgreement          one per employee per period (unique constraint), FK template+version snapshot,
                              revision number (the form's Rev3/Rev4), final_score (Σ), final_band
  ├─ employee, supervisor (snapshotted at creation like Review.manager), status machine:
  │     draft → submitted → returned | agreed(signed) → active → amended(new version) → self_assessed →
  │     supervisor_assessed → moderated → closed → archived
  ├─ HistoricalRecords (amendments = new history rows; agreement number stays)
  ├─ AgreementElement[]: from template + employee-specific rows; section, kpa_description, kpi_title, metric,
  │     weight, level_descriptors {1..5}, order; Q2: q2_target_note, employee/manager comments;
  │     Q4: final_rating (1–5), employee/manager comments, score = weight × rating; (moderated_rating later)
  └─ PDPItem[]: business_process, course/training/certificate → optional link to learning.TrainingRecord

EvidenceItem                  FK element (+ optional review stage), FileField (policies pattern),
                              uploaded_by, description, sha256, authenticated download; never hard-deleted
                              once the agreement is signed (soft-delete + audit)

AgreementSignature            FK agreement, stage (contracting|midyear|final|amendment), role
                              (employee|supervisor|witness|moderator), signer, acting_for (nullable, via
                              SigningDelegation), signed_at, method
                              (password_reauth|totp_stepup), document_sha256 (hash of the PDF snapshot
                              being signed), ip/user-agent; immutable (no update/delete endpoints)

AgreementDocument             the generated PDF snapshot per signed stage (reportlab), stored + hashed;
                              this is what "archiving KPI documents" means concretely

SigningDelegation             delegator (Head), delegate, start/end date, scope; created by delegator or hr_admin;
                              audit-logged; consulted by the signature permission check

ModerationSession (later)     period + department/level scope, committee members, decisions with reasons
```

Existing `Review` (single rating) becomes redundant once agreements exist — either derive its two ratings from the
agreement's final scores (keeps the current Reviews pages alive) or retire it. `Goal` stays as informal goals
(YAGNI: don't force every goal into a contract). `Feedback` untouched.

## 4. Where it lives — three options

| | Option A — extend `performance` in place (**recommended**) | Option B — new app `performance_contracting` | Option C — rebuild `performance` around agreements |
|---|---|---|---|
| Fit with module rules | ✅ one app per domain; `ReviewCycle` becomes the period; no cross-app import problem | ⚠️ needs a `performance/queries.py` seam just to reach `ReviewCycle`, or duplicates the period concept | ✅ |
| Migration risk | low — additive models, `Review` kept/derived | low | high — data migration of `Review`/`Goal`, frontend rewrite |
| Size | 3 sprints (§5) | 3 sprints + boundary plumbing | 4+ sprints |
| Verdict | **Do this.** The existing app is 134 lines of models; there is nothing worth isolating from | Only if the contracting process is owned by a different team and must ship independently | Only if `Review`'s single-rating model is deemed actively harmful — it isn't, it's just thin |

**Signing method options:** (1) click-to-sign + password re-auth + audit + PDF hash — simplest, ECT-Act-adequate;
(2) reuse ADR-009 TOTP step-up as the signature proof — stronger, zero new deps, but forces every employee to enrol
an authenticator (today only payroll roles do); (3) external e-sign vendor — advanced signature, per-envelope cost,
new ADR. **Recommend (1) as the default with (2) offered per template** ("this template requires MFA-signed
agreements", e.g. for SMS/executive contracts) — the `AgreementSignature.method` field carries which was used.

## 5. Sprint shape (if approved — each is one full build/test/browser-verify/push loop)

| Sprint | Scope | Exit |
|---|---|---|
| PC-1 Periods + templates + contracting + **reminder schedule** | period phases **with reminder offsets**; template CRUD/versioning/targeting; agreement drafting from template; element CRUD with weight validation (=1.00); submit/return; **employee-then-Head signature** (method 1); PDF snapshot v1; scheduler job that computes who is outstanding per phase and emits reminders through the collab adapter (PC-0) | employee & manager sign an agreement in the browser; hr_admin sees contracting completion % |
| PC-2 Reviews + evidence + scoring | mid-year/final per-element self/supervisor ratings; evidence upload/download per element (policies pattern); weighted scoring + GAF blend; amendments (re-sign); derive `Review` from agreement | full year simulated end-to-end for one employee across roles |
| PC-3 Moderation + archive + dashboards | moderation session + overrides with reasons; final PDF + archive per period; period close/archive; dashboards (completion by department, rating distribution with small-cell suppression like EE); link final band → `compensation` proposal creation (optional) | period archived; auditor can pull any signed PDF + signature trail |

Cross-cutting prerequisites that these sprints will need and that don't exist yet: **notifications** (sign requests,
deadline reminders) and **Celery** (PDF generation, archiving) — see NEXT_AGENT_BRIEF §3.2/§7.1. PC-1 can ship
with synchronous PDF generation and no reminders; PC-2/3 really want both.

## 6. Open questions to settle against Sentech's internal process (this is the "refine" step)

1. **Reference document:** is there a Sentech PMDS policy / current performance-agreement template (Word/Excel)?
   That defines the element structure, weights, rating scale and signatories in one go.
2. **Period:** financial year (Apr–Mar)? Contracting deadline (e.g. within 4 weeks)? Which reviews are mandatory —
   quarterly, mid-year only, annual?
3. **Structure:** KPA→KPI two-level or flat KPI list? Fixed KPA:GAF split (80/20?) or per level? Rating scale
   1–5 with which labels? Are some KPAs cascaded/locked from a corporate or divisional scorecard?
4. **Who signs, in what order, and can a signature be delegated** (acting manager)? Is an HR/next-level witness
   required? What happens on refusal to sign (dispute path)?
5. **Amendments:** allowed mid-period? Who approves? Full re-sign or supervisor-only?
6. **Moderation:** is there a committee step? Scope (department, level)? Can it override with reason only?
7. **Evidence:** file types/size; per element or per agreement; who can delete; retention after period close
   (ties to `RetentionRule`).
8. **Signature strength:** is click-to-sign + password re-auth acceptable, or is MFA required for some levels
   (executives/SMS)? Any requirement for an external e-sign provider?
9. **Outcome linkage:** does the final rating feed pay progression / bonus (→ `compensation`) and PDPs
   (→ `learning`) inside this system, or is that reported out to SAP?
10. **Templates ownership:** hr_admin only, or can departments own their own templates within an HR-approved
    frame?

## 6a. Integration with the collab platform (added on request, same day)

**Intent (user):** staff manage their individual KPI items, reminders and evidence day-to-day in the collab platform
(`Agentic_development_collab_platform`, GitHub `internal-collaboration-platform`, FastAPI + React), while the HR
system stays the **system of record** and can *instruct* staff — push a critical, company-wide "complete your
performance agreement" to-do that they cannot ignore.

**What the collab platform already has that fits (verified 2026-08-18 by reading `backend/app/`):**

| Collab primitive | Use for KPI contracting |
|---|---|
| `WorkItem` (`models/work.py:156`: title, assignee, status `todo`…, priority, `due_on`, watchers, dependencies) + `GET /work-items/my` | one work item per employee per phase ("Sign your 2026/27 performance agreement — due 30 Apr"), assigned to the employee, watcher = supervisor |
| Announcements with `priority: "critical"` → **blocking modal** + per-department ack-rate report (`announcements/service.py::acknowledgement_report`) | the "company-wide critical to-do" instruction at contracting open / mid-year / final assessment; ack report = who has seen it |
| Realtime per-user topic `user:{id}:notifications` (WS outbox) | live reminders when HR opens a phase or a supervisor returns an agreement |
| Calendars + CPM engine (Phase 5b) | phase deadlines as calendar entries; dependencies (contracting → mid-year → final) |
| Projects / boards | optional: a per-department "Performance 2026/27" project holding everyone's phase items for line managers |

**What is missing on the collab side (prerequisites, both small):**
1. **Machine-to-machine auth** — `auth/deps.py` accepts user bearer JWTs only; there is no service-account / API-key
   path. Needed so the HR backend can create work items/announcements as "HR System", not as a person.
2. **`external_ref` (+ `source`) on `WorkItem`** so the HR system can upsert idempotently
   (`hcm:agreement:{id}:contracting`) and later mark done/cancelled without duplicating.
3. **Outbound webhook or status callback** so a work item marked *done* in collab can notify the HR side (or the
   HR side polls `/work-items?external_ref=…`). Note: "done" in collab must **never** be the source of truth for
   "signed" — the signature only exists in the HR system; the collab item is a pointer with a deep link.

**Identity mapping:** collab users are UUIDs from OIDC (Keycloak proven 2026-08-16); HR employees are keyed by
`employee_number`/work email; ADR-004 plans Entra ID for the HR system too. Map on **work email** now (both hold
it), on the IdP subject once both sit behind the same IdP. Add `Employee.collab_user_id` (nullable) populated by a
lookup, don't hard-code emails in sync payloads.

**Direction of flow (recommended):**

```
HR system (source of truth: periods, templates, agreements, evidence, signatures, scores)
   │  outbound, via a small `integrations/collab.py` adapter + Celery task (retry/backoff), on events:
   │   • period phase opens  → critical announcement (company-wide or per department) + one WorkItem per employee
   │   • agreement returned  → WorkItem re-opened + notification to employee
   │   • deadline approaching→ reminder (collab notification), item priority bumped
   │   • agreement signed    → WorkItem marked done (HR closes it, not the user)
   ▼
Collab platform (staff-facing daily surface: My work, popups, calendar, board per department)
   │  each item deep-links back to `/my-performance/agreements/{id}` in the HR SPA to actually do the work
   ▲  (optional, later) callback when a user marks an item done → HR nudges: "sign it here" — never auto-signs
```

Keep evidence files and signatures **in the HR system only** (POPIA/audit, retention, tiered access); collab gets
titles, due dates and links — no ratings, no scores, no evidence.

**Effect on the sprint shape:** adds a **PC-0 / integration slice** that can run in parallel with PC-1:
collab side — service-account auth + `external_ref` + (optional) callback; HR side — `integrations/collab.py`
adapter, `Employee.collab_user_id`, Celery task (this makes the Celery decision in NEXT_AGENT_BRIEF §3.2 unavoidable
— wire it), and an ADR (**ADR-011: HR→collab task/announcement integration**; ADR-010 stays the agreements +
e-signature decision). PC-1's "contracting phase opens" event is the first real consumer.

**Extra open questions for §6:** 11. Should *every* employee get a collab account (today collab is department-scoped
users)? 12. Is the collab platform allowed to be a hard dependency of the HR flow (if collab is down, does contracting
still open — yes, recommended: outbound-only, best-effort, retried)? 13. One shared IdP for both systems (Entra vs
Keycloak) — decides the identity mapping.

## 7. Recommendation

Feasible and a natural fit: it extends the thinnest module in the system, and every hard part (file storage,
versioning, step-up identity proof, audit, PDF, history) already has a proven pattern in the codebase. Build as
**Option A**, three sprints, click-to-sign default with per-template MFA option. Do **not** start until questions
1–4 above are answered — they change the data model, not just labels. Once answered → write the design spec (ADR-010: performance agreements & e-signature; ADR-011: collab
integration) → plan → PC-0 (integration plumbing) ∥ PC-1.
