# Design Spec — Performance / KPI Contracting (Performance Agreements)

**Date:** 2026-08-18 · **Status:** draft for user review · **Decisions:** ADR-010 (agreements + e-signature +
delegation), ADR-011 (HR → collab reminders/tasks) · **Source material:** `KPI-Contracting-Investigation.md`
(§2a template extraction, user answers 2026-08-18), `ROADMAP-2026-08.md` (PC-0…PC-3).

## 1. Goal

Replace the spreadsheet-based individual scorecard with a scheduled, reminded, signed, evidenced and archived
workflow inside the HCM, using the collab platform as the staff-facing reminder surface, so that KPI contracting and
reviews stop being a last-minute rush and HR receives complete, signed agreements without chasing.

Non-goals (v1): moderation committee, executive-specific form variants, external e-sign vendor, ImprovementPlan
beyond a stub, matrix/project reporting lines, Graph-API OneDrive picker.

## 2. Domain (extends `hcm/backend/performance/`, Option A)

### 2.1 Period and phases
`PerformancePeriod` (rename of `ReviewCycle`; keep the table, add fields; the old cycle types remain valid):
`name` ("2026/27"), `start_date` (1 Apr), `end_date` (31 Mar), `status` draft→contracting→active→midyear→final→closed→archived,
and one `PeriodPhase` row per stage — `stage ∈ {contracting, midyear, final}`, `opens_on`, `due_on`,
`reminder_offsets_days` (JSON list, default `[28,14,7,1]`), `overdue_every_days` (default 7). `hr_admin` creates the
next period from the previous one ("clone with dates +1 year").

### 2.2 Templates
`AgreementTemplate` (versioned like `Policy`): `name`, `version`, `status` draft/published/retired, `period` (FK,
nullable = reusable), targeting M2M to `JobGrade`/`OccupationalLevel`/`Department` (empty = everyone),
`rating_scale` JSON (`{1:"Below Target",…,5:"Exceeded Stretch Target"}`), `evidence_required` bool,
`signature_method` ∈ {password_reauth, totp_stepup}. `TemplateSection` (the FY's Objectives/Perspectives; ordered;
locked). `TemplateElement`: section, `kpa_description`, `kpi_title`, `metric`, `default_weight` (decimal 0–1),
`level_descriptors` JSON `{1..5}`, `order`, `locked`.

### 2.3 Agreements
`PerformanceAgreement`: `period`, `employee`, `head` (snapshotted from `Employee.manager` at creation),
`template` + `template_version`, `revision` (int, starts 1), `status` (see §3), `final_score` (decimal, computed),
`hr_attention` bool (+ reason), `HistoricalRecords`. Unique (`period`, `employee`).
`AgreementElement`: agreement, section name (copied), `kpa_description`, `kpi_title`, `metric`, `weight`,
`level_descriptors`, `order`, `q2_target_note`, `q2_employee_comment`, `q2_head_comment`, `final_rating` (1–5,
nullable), `final_employee_comment`, `final_head_comment`, `score` (= weight × final_rating, computed).
`PDPItem`: agreement, `business_process`, `course_or_training`, optional FK `learning.TrainingRecord`
(created as `REQUESTED` on request — via `learning/queries.py`-style seam if needed; write goes through learning's own
endpoint, not a cross-app import).
Validation: Σ weights = 1.000 (±0.0005) before `submit`; every element needs 5 level descriptors before `submit`.

### 2.4 Evidence
`EvidenceItem`: element, `stage` ∈ {midyear, final}, `kind` ∈ {file, link}, `file` (FileField, `upload_to=
"performance_evidence/%Y/%m/"`, 20 MB cap, extension + content-sniff), `url` (https only, OneDrive/SharePoint/Teams
or any), `description`, `uploaded_by`, `sha256` (files), `added_after_signoff` bool, soft-delete only after the
stage is signed. Download via an authenticated `download` action (copy of `PolicyViewSet.download`).

### 2.5 Signatures and delegation
`AgreementSignature`: agreement, `stage` ∈ {contracting, midyear, final, amendment}, `revision`, `role` ∈
{employee, head}, `signer`, `acting_for` (nullable), `signed_at`, `method`, `document_sha256`, `ip`, `user_agent`.
Immutable — no update/delete endpoints; deleting an agreement is forbidden once any signature exists.
`SigningDelegation`: `delegator` (a Head), `delegate`, `start`, `end`, `created_by`, `reason`; audit-logged;
active if today ∈ [start, end]. `AgreementDocument`: agreement, stage, revision, `pdf` (reportlab, reproduces the
scorecard grid), `sha256`, `generated_at`.

## 3. State machine (per stage, strict order)

```
contracting:  draft ──submit(employee)──▶ submitted ──return(head)──▶ draft
                                          │
                                          └─approve(head)─▶ approved ──sign(employee)──▶ employee_signed ──sign(head|delegate)──▶ agreed
midyear:      agreed ──open(period phase)──▶ midyear_open ─(comments/target notes/evidence)─▶ midyear_employee_signed ──▶ midyear_signed
final:        … ──open──▶ final_open ─(ratings, comments, evidence)─▶ final_employee_signed ──▶ final_signed (final_score frozen)
amendment:    from agreed/midyear_signed ──amend(head or employee, reason)──▶ revision+1, elements editable, back to submitted → … → agreed
close:        period.close → all final_signed agreements → archived (PDF + evidence manifest); unsigned → hr_attention
```

Rules: the Head's sign action is rejected (409) unless the employee signature for that stage+revision exists; a
delegate may sign only while a `SigningDelegation` is active and the record stores `acting_for`; signing = POST with
`password` (re-auth via `authenticate()`) or a valid step-up grant when the template says `totp_stepup`; every
signature is `AuditLogEntry`'d; the PDF for the stage is generated first, its `sha256` recorded on the signature.
`hr_attention` is set when `final_score < 3` (configurable per period: also any element `< 3`), or when a phase passes
`due_on` unsigned.

## 4. Reminders (ADR-011)

A Celery-beat job (`performance.tasks.run_reminders`, daily 07:00 SAST) computes, per open phase, the set of
agreements not yet at the phase's terminal state, and for each due offset emits through `integrations/collab.py`:
- per employee: upsert a collab `WorkItem` (`external_ref = hcm:agreement:{id}:{stage}`, title, `due_on`, priority
  low→normal→high→urgent by offset, assignee = `Employee.collab_user_id`, watcher = Head), deep link to
  `/my-performance/agreements/{id}`; close it when the stage is signed;
- per Head (or active delegate): a digest work item "N of your team outstanding for {stage}";
- at phase open and at first overdue: a **critical** collab announcement (department-scoped) — blocking popup;
- when H3's email/Notification lands: the same events also send email + in-app notification.
Idempotency: `ReminderLog(agreement, stage, offset, channel, sent_at)` prevents duplicates; the job is safe to re-run.
Feature flag `COLLAB_ENABLED`; failures are logged and retried (backoff), never block the workflow.

## 5. Access (reuses rbac_audit; explicit permission class like ee_reporting/assessments)

- employee: own agreements RW while editable, sign own steps, evidence on own elements, read own PDFs.
- line_manager (Head): team agreements (row-scope own_team) — approve/return, comments, ratings, sign, evidence view;
  delegate the same via `SigningDelegation`; team dashboard.
- hr_admin: all — periods, templates, delegation on behalf, read everything, close/archive; **cannot sign** for others.
- auditor: read-only everything incl. signatures/PDFs. Ratings/scores are Sensitive → gated by row-scope + this
  class, consistent with the existing `Review` docstring; not added to `FIELD_TIERS`.

## 6. Frontend

Routes: `/my-performance` (current agreement, stage checklist, sign buttons, evidence upload), `/team-performance`
(Head: list, outstanding, review/sign, delegation), `/performance/periods` + `/performance/templates` (hr_admin),
`/dashboards/performance` (hr_admin/auditor). Uses the shared fetch hook from H2. Signature dialog: PDF preview →
password (or TOTP code) → sign; the Head's button is disabled with the reason until the employee has signed.

## 7. Testing

Backend: state-machine tests per stage incl. wrong-order sign (409), delegate in/out of window, weight validation,
score maths, evidence gate on/off, reminder job idempotency (frozen time), collab adapter contract tests (recorded
responses), PDF hash matches signature. Frontend: Playwright — full year for one employee across employee/Head/
delegate/hr_admin/auditor logins, incl. reminders visible in collab (X0 dev instance) when available.

## 8. Rollout / migration

Existing `ReviewCycle`/`Review` rows stay; PC-2 derives `Review.self_rating/manager_rating` from the agreement's
final score for the current period so old pages keep working; PC-3 hides the legacy pages once a period completes on
the new flow. Seed: one published template for FY 2026/27 mirroring the extracted scorecard structure (generic content,
no personal data), one period with phases, agreements in each state for the demo logins.
