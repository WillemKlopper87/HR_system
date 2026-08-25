# HCM Data Dictionary — Draft v0.1

**Status:** Sprint 0 draft — refine after source-system inventory (action A2) and EEA2/EEA4 spec receipt (A3); sign-off is a Sprint 0 exit criterion.
**Sensitivity tiers** (enforced by the RBAC layer, see `RBAC-Roles.md`): **P** Public · **I** Internal · **S** Sensitive · **R** Restricted.

## Conventions

- All tables: `id` (bigint PK), `created_at`, `updated_at` (audit trail via django-simple-history on every model — not repeated below).
- Effective-dated tables (ADR-002): `valid_from` (date, required), `valid_to` (date, null = current).
- Enumerations use DB-level choices tables where values are statutory (EEA categories), so DEL spec changes are data edits.

## 1. core_hr

### employee (immutable identity)

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee_number | varchar(20), unique | ✔ | P | Sentech staff number; natural key for imports |
| first_name / last_name | varchar | ✔ | P | |
| preferred_name | varchar | | P | |
| national_id_number | varchar(13), encrypted | | R | SA ID; validate check digit; passport_number alt for non-SA |
| passport_number / nationality | varchar | | R | Only if not SA ID holder (A1 scope) |
| date_of_birth | date | ✔ | S | Derivable from SA ID; stored explicitly for passport holders |
| work_email | varchar, unique | ✔ | P | Entra ID matching key for SSO (ADR-004) |
| personal_email / phone | varchar | | I | ESS-editable |
| hire_date | date | ✔ | I | First engagement date |
| user (FK auth user) | FK, null | | — | Linked at SSO first-login |

### employee_version (effective-dated attributes)

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee | FK employee | ✔ | — | |
| valid_from / valid_to | date | ✔/null | — | ADR-002 |
| department | FK department | ✔ | P | |
| job_title | varchar | ✔ | P | |
| occupational_level | FK occupational_level | ✔ | I | **EEA occupational levels** (Top mgmt … Unskilled) — statutory list |
| job_grade | FK job_grade | ✔ | I | Internal grade; maps to pay_band |
| manager | FK employee, null | | I | Reporting line; drives `own_team` RBAC scope |
| employment_status | enum | ✔ | I | permanent / fixed-term / temporary / learner. **Temporary = employed to work < 3 months** (EEA definition; drives the separate "Temporary employees" row in every EEA2/EEA4 matrix) |
| citizenship_status | enum | ✔ | S | sa_citizen_birth_descent / sa_naturalised_pre_1994 / sa_naturalised_post_1994 / foreign_national. **EEA matrices race only citizens; Foreign Nationals are separate M/F columns** (see `EEA-Form-Spec-Notes.md`) |
| location | FK location | ✔ | I | Province needed for EEA2 |
| position | FK position, null | | P | *(roadmap C1)* The specific approved post this version occupies (`establishment.position`, §3); `SET_NULL`. **This column is what makes occupancy derivable** — a post is filled iff a current version points at it. Carried forward across promotions/transfers (`VERSION_CARRY_FIELDS`) so a version change never silently vacates the post; a partial unique index (`one_current_occupant_per_position`, on `valid_to IS NULL`) enforces at most one current occupant per post. Null = predates establishment control, or holds no numbered post |
| contract_end_date | date, null | | P | *(roadmap C1 part 2)* The date this version's fixed-term contract expires. **Meaningful only when `employment_status = fixed_term`; ignored otherwise.** Nullable by design — existing fixed-term employees got no backfill migration; they are surfaced by the `missing_contract_end_date` data-quality check instead (§7 of the C1 part 2 spec), and cleared one-off through Django admin. Carried forward across promotions/transfers (`VERSION_CARRY_FIELDS`), for the same reason `position` is: an unrelated version change must not silently wipe a still-running contract and stop its reminders. Drives the daily expiry-reminder sweep (`core_hr/contract_reminders.py`) and the renew/convert/lapse decision workflow below. Set explicitly (overriding carry-forward) by `decide_contract_action`: the new date on a renewal, `NULL` on a conversion to permanent |
| race | enum | ✔* | S | **EEA categories: African / Coloured / Indian / White** (+ foreign national flags per EEA2). *Required for EE reporting (legal obligation); "not disclosed" allowed pending self-ID |
| gender | enum | ✔* | S | Male / Female per current EEA2 spec (verify against A3; store separately from self-described gender identity if captured) |
| disability_status | enum + detail | | S | Self-ID only; consent-gated |
| race_source / disability_source | enum | ✔ | S | self_identified / hr_captured / imported — data-quality signal for EE reporting |

### employment_event (lifecycle — gap F1)

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee | FK | ✔ | I | |
| event_type | enum | ✔ | I | hire / promotion / transfer / grade_change / termination / contract_conversion / contract_renewal |
| effective_date | date | ✔ | I | |
| termination_reason | enum, null | ✔ if termination | I | **EEA2 movement categories:** resignation / dismissal_misconduct / dismissal_incapacity / operational_requirements / retirement / death / contract_end / other |
| from_version / to_version | FK employee_version | | — | Links the version rows the event closed/opened |
| notes | text | | I | |

### contract_renewal_decision (roadmap C1 part 2 — fixed-term renew / convert / lapse)

The recommend → decide workflow for a fixed-term contract approaching its `employee_version.contract_end_date`.
Spec: `docs/superpowers/specs/2026-08-20-contract-end-date-tracking-design.md`.

**One row per expiry, and the row only exists once someone has acted** — there is no synthetic "pending, nothing
happened yet" row, so the reminder sweep's "who hasn't acted" query runs off `employee_version.contract_end_date`
directly, never off this table. hr_admin may decide without a prior recommendation (the escalation path), in which
case the row is created straight at `status=decided` with every `recommended_*` column null.

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee_version | O2O employee_version | ✔ | I | `CASCADE`; `related_name="contract_renewal_decision"`. One-to-one, which is what makes "already actioned" a database fact rather than a query |
| status | enum | ✔ | I | recommended / decided. `decided` is terminal — there is no undo and no revise (contrast `position_approval_step`, §3, which has a rejection path back to draft; here hr_admin's decision is final and executes immediately) |
| recommended_action | enum, null | | I | renew / convert_permanent / let_lapse. Null on the hr_admin-decides-directly path |
| recommended_by | FK employee, null | | I | `PROTECT`; the line manager who recommended |
| recommended_at | datetime, null | | I | |
| recommended_comment | text | | I | The manager's motivation |
| recommended_end_date | date, null | | I | Meaningful only when `recommended_action = renew` |
| decided_action | enum, null | | I | Same three choices; hr_admin may accept the recommendation as-is or override it |
| decided_by | FK employee, null | | I | `PROTECT`; the deciding hr_admin |
| decided_at | datetime, null | | I | Also the `effective_date` of the resulting lifecycle event |
| decided_comment | text | | I | |
| decided_end_date | date, null | | I | Meaningful only when `decided_action = renew`; becomes the new version's `contract_end_date` |
| resulting_employee_version | FK employee_version, null | | I | `SET_NULL`. The version the decision opened. Null for `let_lapse` — a termination closes the current version without opening a successor |

Deciding **records and executes in one transaction**, the same way `position.decide_step` both records and advances
state: each action calls `Employee.apply_lifecycle_event()`, so the resulting `employment_event` row is ordinary
EEA2 workforce-movement data with no special-casing — `contract_renewal` for a renewal, `contract_conversion` for a
conversion to permanent, `termination` + `termination_reason=contract_end` for a lapse. Both service functions are
guarded to the employee's **current, fixed-term** version: they are the only API-reachable callers of
`apply_lifecycle_event` in the backend, so nothing else prevents a lapse against a permanent employee (corrupt
statutory data) or a decision recorded against a historical version while the event closes the current one.

`simple_history` is enabled (`HistoricalRecords`), so amendments to a row are themselves an audit trail; the
`recommended_by`/`decided_by` columns carry the actor without a separate `log_access` write, the same precedent
`establishment` sets. Access is gated by field tier on the **nested** `contract_renewal_decision` field of
`EmployeeVersionSerializer` (registered Internal in `rbac_audit/tiers.py`) plus a row-relational check that hides
it from the subject of the decision — see `RBAC-Roles.md` for who can actually read and write it.

### employment_change (C1 part 3 — exit state machine & access cascade)

The propose → confirm → execute object for a suspension or an employment exit. Spec:
`docs/superpowers/specs/2026-08-20-employment-exit-states-design.md`.

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee | FK employee | ✔ | — | `CASCADE` |
| change_type | enum | ✔ | I | suspension / lift_suspension / dismissal_summary / dismissal_misconduct / dismissal_incapacity / operational_requirements / resignation / retirement / contract_end / death |
| state | enum | ✔ | I | proposed → confirmed → executed, or cancelled from either non-terminal state. DB-enforced: at most one non-terminal row per employee (`one_open_employment_change_per_employee`) |
| effective_date | date | ✔ | I | When the cascade runs. Forced to today for `dismissal_summary` (immediate by definition); execution is scheduled otherwise — see `core_hr/tasks.py`'s daily sweep |
| reason | text | ✔ | I | Free text; enforced non-blank in the service layer, not the column. "A dismissal without a recorded reason is not defensible" |
| proposed_by / proposed_at | FK employee / datetime | ✔ | I | `PROTECT` |
| confirmed_by / confirmed_at | FK employee, null / datetime, null | | I | `PROTECT`. Tiered types (suspension, lift, and every dismissal ground) require a *different* person from `proposed_by`; routine leavers (resignation/retirement/contract_end/death) may self-confirm |
| executed_at | datetime, null | | I | Set when the cascade runs |
| cancelled_by / cancelled_at / cancellation_reason | FK employee, null / datetime, null / text | | I | `PROTECT`. Only reachable from `proposed`/`confirmed` |
| lifts_suspension | FK employment_change (self), null | | I | `PROTECT`. Set only for `lift_suspension` — the suspension row being reversed |
| revoked_role_assignments | M2M role_assignment | | — | The assignments THIS execution revoked, so a lift restores precisely those (a restored grant is a **new** `role_assignment` row, not an un-revocation of the old one) |
| resulting_event | FK employment_event, null | | — | `SET_NULL`. Null for suspension/lift_suspension, which create no lifecycle event — **suspension is deliberately not a lifecycle event** (§2.1 of the spec): `valid_to` stays null and no `employment_event` row is written, or the EEA2 termination count would be corrupted |

Execution (spec §6) revokes every active `role_assignment`, disables `employee.user.is_active` where a login
exists, suspends the biometric enrolment (`identity_verification.biometric_enrollment.active`, via a registry in
`core_hr/access_cascade.py` so `core_hr` never imports that domain app), and — ending types only — closes
employment through the existing `Employee.apply_lifecycle_event()`. Every step writes an `audit_log_entry`
(`rbac_audit`). **Nothing is deleted**: versions are closed, role assignments are revoked (not removed), and the
`employment_change` row itself is permanent provenance — see the retention note below.

**Retention:** `employment_event` and `employment_change` are both seeded as explicit `retain` rows in
`retention_rule` (`core_hr/migrations/0011_seed_employment_retention_rules.py`) — see spec §7. A dismissal can
reach the CCMA well after the fact, and BCEA practice keeps employment records for three years post-termination at
a minimum; the executor honours only what a rule states, so this turns "nobody has proposed deleting these yet"
into a recorded decision. **Any future rule against `employee`, `employee_version`, `employment_event`, or
`employment_change` other than `retain` is a decision with real legal exposure and belongs in an ADR, not a bare
migration.**

**Known gap, decided deliberately (not silently):** C1 part 2's `decide_contract_action(..., action=let_lapse)`
still calls `apply_lifecycle_event(TERMINATION, termination_reason=CONTRACT_END)` directly — it does **not** create
an `employment_change` row and does not run the access cascade. A contract left to lapse today still ends
employment correctly (the `employment_event`/EEA2 side is unaffected) but does **not** revoke roles, disable
login, or suspend biometric enrolment. Routing it through `employment_change` was considered and deferred: doing
so would require `decide_contract_action` to start requiring a non-blank `reason` (it currently only takes an
optional `comment`) and would introduce a new failure mode (`EmploymentChangeError` if another change is already
in flight) into a workflow whose contract and view layer weren't built with either in mind. The clean fix is a
follow-up once `employment_change` has its own view/API layer: have the `let_lapse` branch construct-and-
immediately-execute a `contract_end` `employment_change` (deriving `reason` from `comment`, defaulting if blank)
in the same transaction.

### department / job_grade / location

Standard reference tables (name, code, active). `department.parent` (FK self) forms the org tree. `job_grade.occupational_level` maps internal grades to EEA levels.

### occupational_level (statutory)

Seeded with the six EEA occupational levels confirmed from the received forms (per EEA9): Top management · Senior management · Professionally qualified & experienced specialists and mid-management · Skilled technical, academically qualified & junior management · Semi-skilled & discretionary decision making · Unskilled & defined decision making.

### dependant / emergency_contact (C2)

Spec: `docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md` §2.2, §2.9. Basic ESS-level records,
structurally identical to `employee` itself (no file, no consent gate, no workflow) — sit in `core_hr` rather than
the new `documents` app, which exists specifically for file storage + the POPIA review queue.

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| dependant.employee | FK employee | ✔ | — | `CASCADE` |
| dependant.first_name / last_name / relationship | varchar / varchar / enum | ✔ | S | spouse / child / parent / other |
| dependant.date_of_birth | date, null | | S | |
| dependant.id_number | varchar(13), blank | | R | The dependant's own ID number — same tier as `employee.national_id_number` |
| emergency_contact.employee | FK employee | ✔ | — | `CASCADE` |
| emergency_contact.name / relationship / phone / alternative_phone / email | varchar / varchar / varchar / varchar / email | name+phone required | S | `relationship` is free text (informational only, nothing branches on it), unlike `dependant.relationship` |
| emergency_contact.is_primary | boolean | ✔ | I | At most one `True` per employee (conditional `UniqueConstraint`) |

Sensitive-tier by default (stricter than the employee's own analogous fields): this is personal data about a
**third party** who holds no seat at this system's RBAC table. Write access is self-or-hr_admin only, not
generic row-scope — see `RBAC-Roles.md`.

## 2. rbac_audit

### role / role_assignment

| Field | Type | Notes |
|---|---|---|
| role.name / description | varchar | Seed list in `RBAC-Roles.md` |
| role.row_scope | enum | all / own_team / self |
| role.field_tiers | m2m tier grants | P/I/S/R read + write grants |
| role_assignment.employee / role | FKs | + granted_by, granted_at (audited); Entra-group mapping table separate |

### audit_log (append-only)

| Field | Type | Notes |
|---|---|---|
| actor | FK employee, null | null = system job |
| action | enum | read_sensitive / create / update / delete / export / login / permission_change |
| entity / entity_id | varchar / bigint | |
| field_tier | enum | Highest tier touched |
| request_id / timestamp / ip | | Partitioned monthly; INSERT-only DB grant; retention ≥ 5 yrs (C5) |

### consent_record (POPIA — C1)

| Field | Type | Notes |
|---|---|---|
| employee or applicant | FK (one of) | |
| purpose | enum | demographic_self_id / assessment / biometric / employee_documents (C2 — gates `id_copy`/`disability_verification` uploads) / other |
| lawful_basis | enum | consent / legal_obligation_EEA — the lawful-basis register in data |
| granted_at / withdrawn_at | timestamptz | Withdrawal never deletes the audit trail |
| text_version | varchar | Which consent wording was shown |

### retention_rule

Per-entity retention metadata (entity, period_months, action: anonymise/delete/retain) executed by scheduled job; e.g. unsuccessful applicants → anonymise after 12 months. C2 (`documents/migrations/0002_seed_retention_rules.py`) seeds `documents.EmployeeDocument` (retain, 84 months documented — deliberately more conservative than `employment_event`'s 36, since contract/qualification evidence can be reached back for longer by a CCMA dispute or SETA audit) and `core_hr.Dependant`/`EmergencyContact` (delete, 1 month — no standalone evidentiary value once stale). No handler is registered yet for the latter two — same "recorded decision, executor is follow-up work" posture several pre-C2 rows already carry.

## 3. establishment (roadmap C1 part 1 — position / establishment control)

A **position** is an approved, individually-numbered post that exists independently of whoever holds it — the
PFMA-style establishment control an SOE needs for approved-vs-filled visibility, post numbering and a vacancy rate.
Spec: `docs/superpowers/specs/2026-08-19-position-establishment-design.md`.

Occupancy is **derived, never stored**: a post is filled iff some current `employee_version` points at it
(`employee_version.position`, §1), so it can never drift out of sync with who is actually employed — the same
reasoning as `employee.current_version`. `recruitment.requisition` gains a `positions` M2M (one requisition, N
identical posts, since `headcount` can exceed 1) linking an open vacancy to the specific approved, vacant posts it
is hiring into; the hire flow then stamps the consumed post onto the new `employee_version`.

### position

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| post_number | varchar(20), unique | ✔ | P | Auto-assigned sequentially at creation (`P-00001`, `P-00002`, …). Survives every change of incumbent and a reject/revise cycle — it is the post's identity, never re-issued |
| title | varchar(200) | ✔ | P | Mirrors `employee_version.job_title` / `requisition.title` |
| department | FK department | ✔ | P | `PROTECT` |
| occupational_level | FK occupational_level | ✔ | I | `PROTECT`; the statutory EEA level the post sits at |
| job_grade | FK job_grade, null | | I | `PROTECT`; nullable, matching `requisition.job_grade`'s existing nullability |
| location | FK location | ✔ | I | `PROTECT`; province needed for EEA2 |
| status | enum | ✔ | I | draft / in_review / approved / rejected. Only `approved` posts are on the establishment and can be linked to a requisition |
| current_step | smallint | ✔ | I | Index into `settings.POSITION_APPROVAL_CHAIN`; meaningful only while `in_review` |
| proposed_by | FK employee, null | | I | `SET_NULL`; the hr_admin who proposed the post |

Derived, not columns: `current_occupant` (the current `employee_version` pointing here), `is_vacant` (`approved`
**and** no current occupant), and the `vacant()` queryset behind the recruiter's position picker and the Positions
page's vacancy-rate stat.

Tiers above are the sensitivity of the data, for consistency with §1 — but unlike `employee_version`, these tables
carry **no per-field tier enforcement**: they have no `rbac_audit/tiers.py` entry, and nothing here is more
sensitive than Internal. Access is gated whole-endpoint and per-action instead (`RBAC-Roles.md`), with the
recruiter's list scoped to approved posts only.

### position_approval_step (append-only)

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| position | FK position | ✔ | I | `CASCADE`; `related_name="approval_steps"` |
| step_index | smallint | ✔ | I | Which step of the chain this decision resolved |
| role | varchar(40) | ✔ | I | **Snapshot** of the role the step required, read from settings at decision time — deliberately not a live reference, so lengthening/reordering the chain later can never rewrite history |
| actor | FK employee, null | | I | `SET_NULL`; who decided |
| decision | enum | ✔ | I | approved / rejected. A rejection stops the chain immediately |
| comment | text | | I | The reviewer's reason |

One row per decision, never updated or deleted; `created_at` (see Conventions) is the decision timestamp.
`revise_and_resubmit` starts a fresh cycle on the same `post_number` and keeps every prior row.

The chain itself is **deployment-time configuration, not a table**: `settings.POSITION_APPROVAL_CHAIN`, an ordered
list of role names (default `["comp_manager", "accounting_officer"]`). Changing it changes who approves and how
many steps, with no code or schema change — see `RBAC-Roles.md` for who may act at each step. Backfilled posts (one
per employee already in service when C1 shipped) carry **no** approval-step rows: that is already-real employment,
not a proposal that went through review.

## 4. onboarding (C1 part 3 slice 3 — onboarding / offboarding checklists)

Spec: `docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md`. One app covering both
directions via a `direction` field (spec §2.1), structurally mirroring `performance.AgreementTemplate`'s
versioned-template shape but deliberately without its signing/scoring machinery (spec §2.3) — a checklist item
is ticked off, not rated or signed.

### checklist_template / checklist_template_item

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| name | varchar(200) | ✔ | I | |
| direction | enum | ✔ | I | onboarding / offboarding |
| version | smallint | ✔ | I | Auto-assigned server-side: `(max version for this name+direction) + 1` — never client-writable |
| status | enum | ✔ | I | draft → published → retired |
| created_by | FK employee, null | | I | `SET_NULL` |
| published_at | datetime, null | | I | |

`UniqueConstraint(name, direction, version)` — extends `AgreementTemplate`'s equivalent constraint with
`direction`, since two directions legitimately share a name+version and version is assigned per name+direction,
not per name alone. `checklist_template_item`: `template` (FK, `CASCADE`), `label` (varchar 300), `description`
(text, blank), `owner_role` (enum: hr / it / line_manager / employee / other — who normally does this, and for
`line_manager` specifically also the completion gate itself, spec §3), `order` (smallint). Editable only while
the template's `status` is `draft` (service-layer rule, not a DB constraint) — publishing freezes the task list
so a later edit never rewrites a checklist instance that already snapshotted it (spec §2.4).

### checklist_instance / checklist_instance_item

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee | FK employee | ✔ | — | `CASCADE` |
| template | FK checklist_template | ✔ | I | `PROTECT` — the exact template version this instance was drawn from |
| template_version / direction | smallint / enum | ✔ | I | Snapshot of the template's own fields at creation |
| status | enum | ✔ | I | active → completed, or cancelled |
| triggering_change | FK employment_change, null | | I | `SET_NULL`. Set only for an offboarding instance created by the automatic exit hook; null for onboarding instances and any manually-created instance |
| created_by | FK employee, null | | I | `SET_NULL`. Null = created by the automatic hire/exit hook; set = the hr_admin who manually triggered it |
| completed_at | datetime, null | | I | Set when every item on the instance is complete |

DB-enforced: at most one **active** instance per employee per direction (`one_active_checklist_per_employee_per_direction`,
a Django 5.2 conditional `UniqueConstraint`), the same shape as `employment_change`'s
`one_open_employment_change_per_employee`. `checklist_instance_item`: `instance` (FK, `CASCADE`),
`label`/`description`/`owner_role`/`order` copied from the template item at creation and never re-synced
(this row's identity *is* the snapshot), `completed_by` (FK employee, null, `SET_NULL`), `completed_at`
(datetime, null — null = not done), `notes` (text, blank).

**Triggers (spec §6):** `core_hr/lifecycle_hooks.py` — a new registry, same shape as `access_cascade.py`/
`data_quality.py` — lets `EmployeeManager.hire()` spawn an onboarding instance and `exits.py`'s ending-type
execution branch spawn an offboarding instance, without `core_hr` (SHARED_KERNEL) importing the `onboarding`
app. A suspension executing does **not** trigger an offboarding instance — a suspended employee hasn't left. No
published template for the direction = the hook is a no-op, never an error; a hire or an exit must never fail
because a checklist template doesn't exist.

## 5. documents (C2 — employee documents & POPIA rights)

Spec: `docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md`. A new peer app (not folded into
`core_hr`/SHARED_KERNEL or `policies`, whose shape is an org-wide broadcast document, the opposite of a private
per-employee file) — see spec §2.1.

### employee_document

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee | FK employee | ✔ | — | `CASCADE` |
| document_type | enum | ✔ | — | id_copy / qualification / employment_contract / disability_verification / other |
| title / description | varchar(200) / text | title required | — | |
| file | file | ✔ | — | `employee_documents/%Y/%m/` |
| content_type | varchar(120), blank | | — | **Server-sniffed** (`documents/validation.py`), never client-trusted — the same content-sniffing fix `policies/extraction.py` established, applied here |
| size_bytes | int | ✔ | — | Capped at 10MB server-side |
| uploaded_by | FK employee, null | | — | `SET_NULL` |

`tier` is a **row-level property** driven by `document_type` (spec §2.6), not a `rbac_audit/tiers.py` FIELD_TIERS
entry — the generic per-field shape doesn't fit a model whose sensitivity varies by row: `id_copy`/
`employment_contract` → Restricted, `disability_verification`/`other` → Sensitive, `qualification` → Internal.
Consent (`rbac_audit.ConsentRecord`, purpose `employee_documents`) is required only for `id_copy`/
`disability_verification` (spec §2.7). Authenticated download reuses `policies.PolicyViewSet.download`'s exact
`FileResponse` pattern — no `MEDIA_URL` static mount exists (`config/urls.py`).

### data_subject_request

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee | FK employee | ✔ | S | `CASCADE` |
| request_type | enum | ✔ | S | export / erasure |
| status | enum | ✔ | S | submitted → completed, or declined |
| requested_by | FK employee, null | | S | `SET_NULL`. Usually == employee; set to the filing hr_admin when the subject can no longer log in (the exit cascade already disabled their login — spec §6.3) |
| requested_at | datetime | ✔ | S | `auto_now_add` |
| request_notes / resolution_notes | text, blank | | S | |
| reviewed_by / reviewed_at | FK employee, null / datetime, null | | S | `SET_NULL`. Set when hr_admin actions the request |
| export_file | file, null | | R | Populated only when an EXPORT request completes — a JSON snapshot, downloaded via the same authenticated `FileResponse` pattern |

DB-enforced: at most one **submitted** (open) request per employee per `request_type` — same conditional-
`UniqueConstraint` shape as `checklist_instance`'s one-active-per-employee-per-direction rule.

Both request types are **reviewed and actioned by hr_admin, never auto-executed** (spec §6.1-6.2). Erasure
(`documents/services.py::complete_erasure_request`) is a **hardcoded allow-list**, not a `retention_rule`-driven
delete — it may only ever touch: every `employee_document` and `dependant`/`emergency_contact` row for the
employee, and exactly three `employee` fields (`preferred_name`, `personal_email`, `phone` — RBAC-Roles.md's own
ESS-editable set). It never touches `employment_event`, `employment_change`, `audit_log`, or `employee_version`
history, regardless of any `retention_rule` state — the non-destructive philosophy the employment-exit-states
spec §6.3 established for the access cascade extends here by construction, not by rule lookup.

## 6. learning — mandatory-training compliance (C6)

Spec: `docs/superpowers/specs/2026-08-25-mandatory-training-compliance-design.md`. Extends the existing
`learning` app (Sprint 8) — `course`/`course_requirement` are new tables; `training_record` gains a nullable
`course` FK.

### course

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| name | varchar(200), unique | ✔ | P | Catalogue identity, mirrors `skill.name` |
| provider | varchar(200), blank | | P | |
| description | text, blank | | P | |
| hours | decimal(6,1), null | | P | |
| mandatory | bool | ✔ (default false) | P | Catalogue metadata — the *kind* of course, not the scoped rule; see `course_requirement` below |
| validity_days | int, null | | P | Renewal cycle in days (e.g. 365 = annual refresher); null = never expires once completed |
| active | bool | ✔ (default true) | P | |

### course_requirement

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| course | FK course | ✔ | P | `PROTECT` — mirrors `employee_skill.skill` |
| department | FK department, null | | P | `PROTECT`. Null = not scoped by department |
| occupational_level | FK occupational_level, null | | P | `PROTECT`. Null = not scoped by level |
| effective_from | date | ✔ | P | Rules can be added after people are already employed — the clock for anyone already in scope starts here, not at their hire date |
| due_within_days | int | ✔ | P | Grace period from "became subject to this rule" to due |
| active | bool | ✔ (default true) | P | Retire a rule without deleting it |

Both null (`department` and `occupational_level`) means an organisation-wide mandate. **No DB-level uniqueness**
on `(course, department, occupational_level)` — `NULL` isn't equal to itself under SQL uniqueness semantics, so
a `UniqueConstraint` would not catch two org-wide rules for the same course, the likeliest accidental duplicate.
`CourseRequirementSerializer.validate()` checks for an existing active duplicate instead (treating `None` as
equal to `None`), and separately rejects a requirement targeting a non-`mandatory` course (spec §2.2/§4.2).

Scoping FK choice (`department`/`occupational_level`, not `job_title`/`position`/`job_grade`) — full
investigation in spec §2.3, summarised in `RBAC-Roles.md`'s C6 section.

**Compliance is derived, never stored** — no `compliance_record` table. `learning/compliance.py` computes, on
read, which requirements apply to an employee (matched against their current `employee_version`'s `department`/
`occupational_level`) and whether a `training_record(course=X, status=completed)` satisfies each one within its
validity window. Same "derive, don't store" philosophy as `establishment.position.current_occupant` (§3 above).

## 7. succession — succession planning / talent pools (C6)

Spec: `docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md`. New app, not `SHARED_KERNEL`.

### critical_post

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| position | FK establishment.position, unique | ✔ | — (row-level, see below) | `PROTECT`. One row per post ever flagged; `active` toggles the flag rather than a second row |
| reason | text, blank | | — | Why this post is succession-critical |
| active | bool | ✔ (default true) | — | Flag/unflag without deleting, mirrors `course.active` |
| flagged_by | FK employee, null | | — | `SET_NULL` |

Read audience matches `establishment.position` itself (hr_admin, comp_manager, accounting_officer, auditor,
recruiter) — the flag is Position-adjacent metadata, not the sensitive nominee list below. Not a `FIELD_TIERS`
entry — gated whole-endpoint by `CriticalPostPermission`, same shape as `ChecklistTemplatePermission`.

### succession_candidate

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| critical_post | FK critical_post | ✔ | — (row-level) | `CASCADE` |
| employee | FK employee | ✔ | — (row-level) | `CASCADE` — the nominated successor |
| readiness | varchar, choices | ✔ | — (row-level) | `ready_now` / `ready_1_2_years` / `ready_3_plus_years` / `development_needed` |
| notes | text, blank | | — (row-level) | |
| nominated_by | FK employee, null | | — (row-level) | `SET_NULL` |
| active | bool | ✔ (default true) | — (row-level) | Withdraw without deleting; multiple historical rows per (critical_post, employee) pair are allowed |

`UniqueConstraint(critical_post, employee) WHERE active` — at most one active nomination per pair, same
conditional shape as `checklist_instance`'s one-active-per-employee-per-direction rule. **Deliberately not a
`FIELD_TIERS` entry** — this whole model is sensitive, not a subset of its fields, so it's gated whole-endpoint
(`SuccessionCandidatePermission`: hr_admin manages it, hr_admin/auditor read it) exactly like
`performance.review`/`feedback`'s own documented exception. Read access is **narrower than a normal
Internal-tier field**: no role gets self-scope here at all, including hr_admin viewing their own row — the
viewset's own `get_queryset` excludes the acting requester's `employee_id` regardless of role (spec §2.6/§5.2).

Both `skill_names`/`latest_performance` on the API response are **read-only cross-app context, not stored
columns** — `learning/queries.py::skill_names_for_employee` and the new `performance/queries.py::
latest_final_score` read seams, informational only, never an input to `readiness` (spec §2.7).

## 8. recruitment — interview scheduling, panel scorecards, background checks, careers portal (C6)

Spec: `docs/superpowers/specs/2026-08-25-recruitment-interviews-careers-portal-design.md`. Extends the existing
`recruitment` app (Sprint 4) rather than a new one — three new models, plus new fields on `requisition` and
`applicant`.

### requisition (fields added)

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| description | text, blank | | I | Free-text job description — general-purpose, not portal-exclusive |
| external_posting | bool | ✔ (default false) | I | HR opts a requisition INTO public visibility; no open requisition is public by default |

### applicant (fields added)

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| source | varchar, choices | ✔ (default internal) | P | `internal` / `portal` — provenance only, never read by the stage machine, retention handler, or hire flow |
| resume | file, null | | I | Server-sniffed content type (`recruitment/validation.py`), never client-trusted; settable by a recruiter PATCH too, not portal-only |
| resume_content_type | varchar, blank | | I | |
| resume_size_bytes | int | ✔ (default 0) | I | |

### interview_session

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| applicant | FK applicant | ✔ | — (row-level) | `CASCADE`. Serializer requires `applicant.current_stage == interview` at create |
| round_number | int | ✔ (default 1) | — | Multiple rounds = multiple rows, ordered by round |
| scheduled_at | datetime | ✔ | — | |
| duration_minutes | int | ✔ (default 60) | — | |
| location | varchar(300), blank | | — | Free text — a room name or a video-call URL; no calendar integration |
| status | varchar, choices | ✔ (default scheduled) | — | scheduled / completed / cancelled |
| notes | text, blank | | — | Recruiter's own logistics notes, distinct from a scorecard's per-interviewer notes |
| interviewers | M2M employee | | — (row-level) | The panel — plain M2M, no through-model |
| created_by | FK employee, null | | — | `SET_NULL` |

Read/write: **recruiter, hr_admin** full access; an assigned interviewer gets **read-only access to their own
sessions** — a row-level grant (`interviewers` membership), not a role, since any employee can be tapped as a
panelist. Not a `FIELD_TIERS` entry — gated whole-endpoint by `IsRecruiterOrHRAdminOrAssignedInterviewer`.

### interview_scorecard

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| session | FK interview_session | ✔ | — (row-level) | `CASCADE` |
| interviewer | FK employee | ✔ | — (row-level) | `CASCADE`. Force-set server-side to the authenticated actor — never client-supplied |
| skill_rating | smallint, choices 1-5 | ✔ | — (row-level, blind) | Matches `performance`'s own 1-5 rating vocabulary |
| communication_rating | smallint, choices 1-5 | ✔ | — (row-level, blind) | |
| culture_fit_rating | smallint, choices 1-5 | ✔ | — (row-level, blind) | |
| comments | text, blank | | — (row-level, blind) | |
| recommendation | varchar, choices | ✔ | — (row-level, blind) | strong_hire / hire / no_hire / strong_no_hire |

`UniqueConstraint(session, interviewer)` — one scorecard per interviewer per session. **Blind review**: the
five fields marked "blind" above are hidden from any viewer other than the row's own interviewer or a recruiter/
hr_admin, until the viewer has submitted their own scorecard for that same session — enforced in
`InterviewScorecardSerializer.to_representation`, not a `FIELD_TIERS` entry (this is an anti-anchoring
visibility rule keyed on the VIEWER's own submission state, not a static role/tier grant, so it doesn't fit
that machinery). Write: **the named interviewer only** — no proxy-entry, not even by hr_admin.

### background_check

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| applicant | FK applicant | ✔ | — (whole-model S) | `CASCADE` |
| check_type | varchar, choices | ✔ | — (whole-model S) | reference / criminal_record / qualification_verification / credit_check / other |
| status | varchar, choices | ✔ (default not_started) | — (whole-model S) | not_started / requested / in_progress / cleared / flagged — no `ALLOWED_TRANSITIONS` state machine; a real vetting process can move non-monotonically (e.g. flagged → cleared after review) |
| requested_by | FK employee, null | | — (whole-model S) | `SET_NULL` |
| requested_at | datetime, null | | — (whole-model S) | |
| completed_at | datetime, null | | — (whole-model S) | |
| notes | text, blank | | — (whole-model S) | Can legitimately hold criminal-record or credit-check detail |

Tracking only — no vendor integration (`docs/MVP-Backlog.md` A3 #9). **Deliberately not a `FIELD_TIERS`
entry** — the whole model is Sensitive by nature, gated whole-endpoint by the existing `IsRecruiterOrHRAdmin`
(same audience as `requisition`/`applicant`/`offer`). **No interviewer access at all** — unlike
`interview_session`/`interview_scorecard`, there is no row-level carve-out here.

### Careers portal (public, unauthenticated)

`GET /api/v1/careers/postings/` (list/detail) and `POST /api/v1/careers/apply/` are `AllowAny` — the system's
first genuinely public, unauthenticated, write-capable surface. A successful submission creates a real
`applicant` row (`source=portal`) via `recruitment/services.py::submit_portal_application`, gated by:
content-sniffed resume validation (`recruitment/validation.py`, 5MB cap — duplicates `documents/validation.py`'s
approach rather than importing it, a peer-app boundary), three new throttle scopes in `rbac_audit/throttling.py`
mirroring `LOGIN_THROTTLES`'s burst/sustained/identifier-keyed shape exactly (`careers_application_burst`,
`careers_application_sustained`, `careers_application_email`), and a honeypot field. Optional demographic
fields (`race`/`gender`/`disability_status`) follow the same not_disclosed-default, consent-gated posture as
the internal flow — **consent gates storage of the answer, not submission of the application**: an unconsented
value is silently dropped rather than blocking the applicant's whole submission.

## 9. Later-sprint entities (summary — detail in the owning sprint)

| Module | Entities (tier of most sensitive field) | Detailed in |
|---|---|---|
| recruitment | requisition (I), applicant (S — demographics, consent-gated), application_stage (I), offer (R — pay); since C6, also interview_session/interview_scorecard (row-level, blind-review) and background_check (whole-model S) — see §8 | Sprint 4, C6 |
| performance | goal (I), review_cycle (I), review (S — ratings), feedback (S) | Sprint 6 |
| learning | skill (P), employee_skill (I), certification (I), training_record (I — feeds WSP/ATR, and since C2, so does certification; since C6, `course` FK is also I) | Sprint 8 |
| compensation | pay_band (R, effective-dated), comp_proposal (R), benefits_election (S) | Sprint 10 |
| assessments | assessment_assignment (S), assessment_result (S), provider_config (I) | Sprint 12 |
| ee_reporting | ee_snapshot (S, immutable), ee_report (S, versioned + sign-off chain ending at CEO/Accounting Officer), ee_plan (I — 5-yr sector targets + annual targets per level×group×gender + disability targets), ee_questionnaire (I — justifiable reasons, consultation, 24-category barriers/AA grid, monitoring), employer_config (I — Section A identity: DTI/PAYE/UIF/EE ref, SETA classification, EAP choice), **remuneration_record (R — per-employee annualised fixed + variable remuneration imported from SAP payroll; required to generate EEA4)** | Sprint 13 (spec: `EEA-Form-Spec-Notes.md`) |

## Open data questions

1. ~~Exact EEA2/EEA4 field layout~~ → **Resolved 2026-08-12**: forms received and analysed; see `EEA-Form-Spec-Notes.md`. Still outstanding: the DEL *online portal* upload format (the forms define content, not the electronic file schema) — confirm at first submission rehearsal.
2. Which spreadsheets/SAP tables hold current demographics, and their race/gender coding schemes (mapping tables needed for import) (A2 — sources named, detail inventory outstanding).
3. ~~Foreign-national treatment~~ → **Resolved**: FN are separate Male/Female columns, not raced; race applies to citizens only. Captured via `citizenship_status`.
4. Whether Sentech grades map 1:1 to EEA occupational levels or need a mapping review with HR (A2).
5. **New:** SAP payroll extract feasibility and format for `remuneration_record` (fixed vs. variable split per EEA4 definitions) — folds into action A10.
