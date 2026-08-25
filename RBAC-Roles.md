# RBAC Role Definitions — Draft v0.1

**Status:** Sprint 0 draft — the Sprint 0 task "Define role list for RBAC". Becomes seed data for the Sprint 2 build.
**Model:** a role = model permissions + **field-tier grants** (P/I/S/R per `Data-Dictionary.md`) + a **row scope** (all / own_team / self). Roles are DB rows; Entra ID groups map to roles at login; in-app grants are audited.

## Roles

| Role | Row scope | P | I | S | R | Purpose / notes |
|---|---|---|---|---|---|---|
| **employee** (default, everyone) | self | RW* | R | R (own) | R (own pay slip-level only if surfaced) | ESS: own profile, own consent, own reviews. *W on ESS-editable fields only (contact details, self-ID via consent flow) |
| **line_manager** | own_team | R | R | **aggregate-only** | — | Team views; demographics only as suppressed aggregates (n ≥ 5); sees own team's reviews/goals; no pay |
| **hr_admin** | all | RW | RW | RW | R | Core HR data management, imports, data-quality queue. Restricted-tier *read* for support; comp changes still go via comp workflow |
| **ee_manager** | all | R | R | RW | — | EE reporting, self-ID campaign, EEA sign-off chain. No pay access |
| **recruiter** | all (recruitment module) | RW | RW | S: applicant demographics R (consent-gated) | offer pay: RW within band | No access to employee performance/comp modules |
| **comp_manager** | all | R | R | R (aggregate) | RW | Pay bands, comp review workflow, benefits config |
| **auditor** | all | R | R | R | R | **Read-only everywhere**, including audit log; every auditor read is itself audited |
| **sysadmin** | all | — | — | — | — | Technical operations: user/role mapping, integrations, jobs. **No standing access to S/R business data**; break-glass elevation is logged and alerts hr_admin |
| **accounting_officer** | all | — | — | — | — | *(Added Sprint 13–14, EEA-Form-Spec-Notes.md)* Final EEA2/EEA4 sign-off (PFMA employer). No standing access to S/R business data outside that one approval action — same reasoning as sysadmin |

## Standing rules

1. **Aggregate small-cell suppression:** any demographic aggregate exposed to a role without S-read suppresses cells with n < 5 (configurable) — applies to line_manager dashboards and all org-wide dashboards (gap C6).
2. **Reads of S/R fields are audited**, not just writes (Sprint 2 acceptance criterion).
3. **No role bypasses the API permission layer** — Django admin access is limited to hr_admin + sysadmin and wrapped by the same field-tier checks.
4. **Segregation of duties:** the proposer of a comp change cannot be its approver; sign-off chains enforce distinct actors (ApprovalChain primitive).
5. Role changes are themselves R-tier audited events.

## Module access: establishment / positions (roadmap C1)

The `Position` endpoints are the one set whose write access is decided **per record and per step** rather than per
role, so they don't reduce to a row in the table above. Enforced by `establishment/permissions.py` (the coarse
gate) plus per-action checks in `establishment/views.py`.

| Action | Roles allowed |
|---|---|
| Read — `GET /api/v1/positions/` | hr_admin · comp_manager · accounting_officer · auditor · recruiter. **recruiter sees `status=approved` only** — they need vacant posts to build a requisition, not the approval-chain detail of in-review ones. Every other role (line_manager, employee, ee_manager, sysadmin) gets 403 |
| Propose (`POST /positions/`), submit (`/submit/`), revise (`/revise/`) | **hr_admin only** |
| Decide a chain step (`POST /positions/{id}/decide/`) | Whichever role `settings.POSITION_APPROVAL_CHAIN[current_step]` names — by default comp_manager at step 0, then accounting_officer. Any other role gets 403, *including* one that appears elsewhere in the same chain |

The `WRITE_ROLES` gate in `permissions.py` (hr_admin · comp_manager · accounting_officer) is deliberately coarser
than these rules: it only decides who may reach a POST at all, and the per-action checks then decide who may
actually perform it — wrong role at a step is a 403, wrong *state* is a 400. Changing `POSITION_APPROVAL_CHAIN`
changes the decide row with no code change and no edit here; the frontend reads the required role off the API
(`next_approver_role`) rather than re-deriving it, so a different chain shape needs no UI change either.

## Module access: contract renewals (roadmap C1 part 2)

Two POST actions on `EmployeeVersionViewSet` (`core_hr/views.py`) plus the read surface of the
`contract_renewal_decision` they produce. Spec:
`docs/superpowers/specs/2026-08-20-contract-end-date-tracking-design.md`.

| Action | Roles allowed |
|---|---|
| Recommend — `POST /api/v1/employee-versions/{id}/recommend_contract/` | **line_manager, and only for an employee in their own reporting chain.** The check is `has_role(actor, "line_manager") **and** is_in_reporting_chain(actor, subject)` — deliberately both. `has_role` is scope-blind and `RowScopePermission` grants object access if *any* active role covers the target, so `has_role` alone would let anyone holding line_manager **plus** any `row_scope=all` role recommend for the whole organisation. That combination is normal in production: line_manager is derived from having direct reports (see the group-mapping table below), so an hr_head or ee_manager with reports holds both. `is_in_reporting_chain` is transitive, so a skip-level manager may also recommend; the UI offers the button to the direct manager only |
| Decide — `POST /api/v1/employee-versions/{id}/decide_contract/` | **hr_admin only** (all-scope by design — deciding is an HR act, not a team-scoped one). Any other role gets 403, *including* the recommending manager and an auditor with full row access |
| Read — the nested `contract_renewal_decision` on `GET /api/v1/employee-versions/…` | Any role whose row scope reaches the record **and** which holds `I:read` — that is **hr_admin · auditor · ee_manager · recruiter · comp_manager** (all `row_scope=all`), plus the subject's own line_manager (`own_team`). `sysadmin` and `accounting_officer` are excluded because both hold `I:read=False`. **On top of that**, the record's own subject is hidden from their decision unless they separately hold one of hr_admin/auditor/manager-of-themselves — a row-relational gate in `core_hr/serializers.py`, not a tier one, since the base `employee` role's self scope grants `I:read` on their own row |

The read surface is genuinely wider than the C1 part 2 spec's §6 table first claimed, and that is **documented
rather than "fixed"**. Field tiers gate by *data sensitivity*, not identity — that invariant is what makes
`FIELD_TIERS` readable at a glance — so adding a per-role allowlist there to exclude ee_manager/recruiter/
comp_manager would break it for every other consumer. A dedicated endpoint instead would mean duplicating the
row-scope + field-tier + subject-gate stack the sprint plan's hard rule exists to prevent. Internal was still the
right tier: it admits every intended consumer and excludes `sysadmin`, which was the actual over-exposure.

Wrong role is a 403 from the view; wrong *state* (already recommended, already decided, not fixed-term, not the
current version, a renewal end date that isn't after the current one) is a 400 from
`core_hr/contracts.py` — the same split `establishment` uses.

## Module access: onboarding / offboarding checklists (C1 part 3 slice 3)

Spec: `docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md` §7. Two model pairs:
`ChecklistTemplate`/`ChecklistTemplateItem` (the process definition) and `ChecklistInstance`/
`ChecklistInstanceItem` (one employee's live checklist).

| Action | Roles allowed |
|---|---|
| Read a template / its items (`GET /checklist-templates/`, `/checklist-template-items/`) | **hr_admin · auditor** |
| Create/publish/retire a template, add/edit/remove its items | **hr_admin only** |
| List/read checklist instances (`GET /checklist-instances/`, `/checklist-items/`) | **hr_admin · auditor** — all; **line_manager** — instances for employees in their reporting chain (`is_in_reporting_chain`, the same check contract-renewal's recommend action uses); **any employee** — their own instance only |
| Manually create an instance (`POST /checklist-instances/`) | **hr_admin only** — the automatic path (hire / exit execution) covers the normal case; this is the backfill fallback |
| Complete/reopen a task (`POST /checklist-items/{id}/complete/`, `/reopen/`) | **hr_admin** — any task; **line_manager** — only a task whose `owner_role` is `line_manager`, only for their own reporting chain; **nobody else**, including the checklist's own subject — an employee can see their own checklist but never ticks a row themselves (design spec §3, decision 1: several tasks are attestations *about* the employee, not *by* them) |

Row visibility for instances/items is decided in each viewset's `get_queryset` (not a blanket permission class),
the same split `EmployeeVersion`'s nested `contract_renewal_decision` read gate uses. Task completion's
`owner_role` + reporting-chain gate is checked directly in the `complete`/`reopen` actions rather than a
permission class, for the same reason the tiered-confirmation rule in the exit state machine lives in
`exits.py`'s service layer: it needs the specific row's data, not just the actor's role.

## Module access: employee documents & POPIA rights (C2)

Spec: `docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md`. New app `documents`
(`EmployeeDocument`, `DataSubjectRequest`); new `core_hr` models `Dependant`/`EmergencyContact`.

| Action | Roles allowed |
|---|---|
| Create/update/delete an `EmployeeDocument` | **Self or hr_admin only** — deliberately narrower than generic row-scope (spec §2.8): no line_manager, even for their own reports |
| Read/download an `EmployeeDocument` | Row-tier gated per `document_type`'s tier (spec §2.6 table) via `can_access_tier_for_target` — self sees all own tiers; **hr_admin** all; **auditor** all; **ee_manager** Sensitive+ org-wide (disability_verification); **comp_manager** Restricted org-wide (id_copy, employment_contract); **line_manager** Internal only (qualification), own team |
| `POST /employee-documents/consent/` (required before an `id_copy`/`disability_verification` upload) | Self or hr_admin |
| Create/read/update/delete a `Dependant`/`EmergencyContact` | **Self or hr_admin only**, full stop — no row-scope extension to line_manager/ee_manager/etc. (spec §2.8-2.9; third-party personal data) |
| Submit a `DataSubjectRequest` (`POST /data-subject-requests/`) | Self, or hr_admin filing on someone's behalf (spec §6.3 — the exit cascade already disabled their login) |
| List/read `DataSubjectRequest`s | Self (own); **hr_admin** all; **auditor** all (read-only) |
| `complete`/`decline` a `DataSubjectRequest` | **hr_admin only** — reviewed and actioned, never auto-executed (spec §6.1-6.2) |

`EmployeeDocument`'s tier is a row-level property (`document_type`-driven), not a `rbac_audit.tiers.FIELD_TIERS`
entry — sensitivity varies by row (an ID copy and a qualification certificate share a model and a `file` field but
are not equally sensitive), which the generic per-field tiering shape doesn't express. Read access is computed per
row via `can_access_tier_for_target`, the same helper `TieredModelSerializer` uses per field, just applied at row
granularity here instead.

## Module access: mandatory-training compliance (C6)

Spec: `docs/superpowers/specs/2026-08-25-mandatory-training-compliance-design.md`. Extends `learning`
(no new app): `Course`/`CourseRequirement` (catalogue + scoped rule), `TrainingRecord.course` (nullable FK).
Compliance is derived on read (`learning/compliance.py`), never stored.

| Action | Roles allowed |
|---|---|
| Read `Course`/`CourseRequirement` (catalogue browsing, dropdowns) | Any authenticated employee — Public tier, same reasoning as `Skill` |
| Create/update/delete `Course`/`CourseRequirement` | **hr_admin only** |
| `GET /dashboards/learning/training-compliance/` (aggregate completion rate by course, org-wide + by department/occupational level) | **hr_admin only** — no per-employee names in the response, same gate/reasoning as `skills_inventory` (spec §5.3) |
| `GET /dashboards/learning/training-compliance/overdue/` (named overdue-individuals list) | **Row-scoped**, not org-wide-by-default — reuses `row_scoped_queryset` exactly as `team_development` already does: `line_manager` sees only their own reporting chain, `hr_admin`/`auditor`/other all-scope roles see everyone, a base `employee` sees only themselves (spec §5.4) |

Scoping FK choice for `CourseRequirement`: `Department` and `OccupationalLevel`, both optional (both null =
organisation-wide mandate). `job_title` was rejected as too unreliable (free text — the exact defect this
feature exists to fix, applied to a different field); `establishment.Position` was rejected as too granular
(an individually-numbered post, not a role type); `job_grade` was considered and set aside as a pay-banding
concept layered under `occupational_level`, not an independent axis any worked example needed. See spec §2.3
for the full investigation.

## Module access: succession planning / talent pools (C6)

Spec: `docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md`. New app `succession` (not
`SHARED_KERNEL` — nothing needs a reverse FK into it): `CriticalPost` (flag on `establishment.Position`) and
`SuccessionCandidate` (nominee + readiness, scoped to one `CriticalPost`).

| Action | Roles allowed |
|---|---|
| Read `CriticalPost` (the flag itself — which posts matter, and why) | Same audience `establishment.Position` is already readable to: **hr_admin · comp_manager · accounting_officer · auditor · recruiter** |
| Create/update `CriticalPost` | **hr_admin only** |
| Read `SuccessionCandidate` (the successor list — who, how ready) | **hr_admin · auditor only.** No other role — including the nominated employee's own login and their line_manager — reaches this at all. On top of the role gate, `SuccessionCandidateViewSet.get_queryset` excludes any row whose `employee` is the acting requester themself, **regardless of role** — an hr_admin or auditor cannot read a row about themself through this endpoint either. This is deliberately stricter than a normal Internal-tier field (which the base `employee` role reads for itself by default): a successor list is a comparative, exclusionary judgement about *other* people, and absence from it is itself sensitive (spec §2.6) |
| Create/update `SuccessionCandidate` (nominate, change readiness/notes, withdraw) | **hr_admin only** — no manager-nominates/hr_admin-confirms two-step chain; hr_admin authors directly, the same single-actor pattern `Course`/`CourseRequirement`/`ChecklistTemplate` already use |

Scoping decision: tied to `establishment.Position` via a `OneToOneField`, not a broader Department/
OccupationalLevel "role track" the way `CourseRequirement` is — a critical post is one specific seat (continuity
for *that* seat), not a population a rule can apply to uniformly. See spec §2.2 for the full investigation
(including why the Department/OccupationalLevel shape that fits mandatory-training compliance doesn't fit
this feature).

## Module access: interview scheduling, panel scorecards, background checks, careers portal (C6)

Spec: `docs/superpowers/specs/2026-08-25-recruitment-interviews-careers-portal-design.md`. All four sub-parts
land in the existing `recruitment` app (direct `Applicant`/`Requisition` extensions, not a new domain) — three
new models (`InterviewSession`, `InterviewScorecard`, `BackgroundCheck`) plus a new public surface
(`recruitment/careers.py`).

| Action | Roles allowed |
|---|---|
| `InterviewSession` create/update/delete, list-all | **recruiter, hr_admin** (`IsRecruiterOrHRAdminOrAssignedInterviewer`) |
| `InterviewSession` read own assigned sessions | Any employee named in `interviewers` for that specific row — a **row-level**, not role-level, grant (being tapped as a panelist isn't tied to any role above). `?mine=true` forces this scoping even for recruiter/hr_admin, so "My Interviews" means their own panel assignments, not the admin view of every session |
| `InterviewScorecard` create/update (own only) | **The named `interviewer` only** — force-set server-side, never client-supplied. Not even hr_admin may author or edit another interviewer's scorecard (no proxy-entry) |
| `InterviewScorecard` read | **recruiter/hr_admin: full detail, always.** Any interviewer on the session: their own scorecard always; a peer's rating/comments/recommendation are hidden (blind review, anti-anchoring) until the viewer has submitted their own scorecard for that same session — then every scorecard on it unlocks together |
| `BackgroundCheck` — all actions | **recruiter, hr_admin only** (`IsRecruiterOrHRAdmin`, unchanged shape). **No interviewer access at all** — a real vetting outcome (criminal/credit checks especially) is exactly the kind of thing an interviewer forming an independent impression should not see. Tracking only — no vendor integration, per `docs/MVP-Backlog.md` A3 #9 |
| Careers portal — `GET /careers/postings/`, `POST /careers/apply/` | **`AllowAny` — no login.** The system's first genuinely public, unauthenticated, write-capable surface. Throttled per-IP (burst + sustained) and per submitted email (mirrors `LOGIN_THROTTLES`'s exact shape in `rbac_audit/throttling.py`) |

`Requisition.external_posting` (default `False`) is the deliberate opt-in a recruiter/hr_admin sets per
requisition — no open requisition is public by default. A portal submission creates a real `recruitment.
Applicant` row (`source=portal`) through the same `Applicant` model, stage machine, and retention/anonymisation
path every internally-sourced applicant uses — consent gates *storage* of the optional race/gender/
disability_status answers, not *submission* of the application itself.

## Entra ID group mapping (draft — confirm names with IT, ADR-004)

| Entra group | Role |
|---|---|
| `HCM-HR-Admins` | hr_admin |
| `HCM-EE-Managers` | ee_manager |
| `HCM-Recruiters` | recruiter |
| `HCM-Comp-Managers` | comp_manager |
| `HCM-Auditors` | auditor |
| `HCM-SysAdmins` | sysadmin |
| `HCM-Accounting-Officers` | accounting_officer |
| (all staff) | employee; line_manager derived from having direct reports in `employee_version.manager`, not from a group |
