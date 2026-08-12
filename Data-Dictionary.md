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
| race | enum | ✔* | S | **EEA categories: African / Coloured / Indian / White** (+ foreign national flags per EEA2). *Required for EE reporting (legal obligation); "not disclosed" allowed pending self-ID |
| gender | enum | ✔* | S | Male / Female per current EEA2 spec (verify against A3; store separately from self-described gender identity if captured) |
| disability_status | enum + detail | | S | Self-ID only; consent-gated |
| race_source / disability_source | enum | ✔ | S | self_identified / hr_captured / imported — data-quality signal for EE reporting |

### employment_event (lifecycle — gap F1)

| Field | Type | Req | Tier | Notes |
|---|---|---|---|---|
| employee | FK | ✔ | I | |
| event_type | enum | ✔ | I | hire / promotion / transfer / grade_change / termination / contract_conversion |
| effective_date | date | ✔ | I | |
| termination_reason | enum, null | ✔ if termination | I | **EEA2 movement categories:** resignation / dismissal_misconduct / dismissal_incapacity / operational_requirements / retirement / death / contract_end / other |
| from_version / to_version | FK employee_version | | — | Links the version rows the event closed/opened |
| notes | text | | I | |

### department / job_grade / location

Standard reference tables (name, code, active). `department.parent` (FK self) forms the org tree. `job_grade.occupational_level` maps internal grades to EEA levels.

### occupational_level (statutory)

Seeded with the six EEA occupational levels confirmed from the received forms (per EEA9): Top management · Senior management · Professionally qualified & experienced specialists and mid-management · Skilled technical, academically qualified & junior management · Semi-skilled & discretionary decision making · Unskilled & defined decision making.

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
| purpose | enum | demographic_self_id / assessment / other |
| lawful_basis | enum | consent / legal_obligation_EEA — the lawful-basis register in data |
| granted_at / withdrawn_at | timestamptz | Withdrawal never deletes the audit trail |
| text_version | varchar | Which consent wording was shown |

### retention_rule

Per-entity retention metadata (entity, period_months, action: anonymise/delete/retain) executed by scheduled job; e.g. unsuccessful applicants → anonymise after 12 months.

## 3. Later-sprint entities (summary — detail in the owning sprint)

| Module | Entities (tier of most sensitive field) | Detailed in |
|---|---|---|
| recruitment | requisition (I), applicant (S — demographics, consent-gated), application_stage (I), offer (R — pay) | Sprint 4 |
| performance | goal (I), review_cycle (I), review (S — ratings), feedback (S) | Sprint 6 |
| learning | skill (P), employee_skill (I), certification (I), training_record (I — feeds WSP/ATR) | Sprint 8 |
| compensation | pay_band (R, effective-dated), comp_proposal (R), benefits_election (S) | Sprint 10 |
| assessments | assessment_assignment (S), assessment_result (S), provider_config (I) | Sprint 12 |
| ee_reporting | ee_snapshot (S, immutable), ee_report (S, versioned + sign-off chain ending at CEO/Accounting Officer), ee_plan (I — 5-yr sector targets + annual targets per level×group×gender + disability targets), ee_questionnaire (I — justifiable reasons, consultation, 24-category barriers/AA grid, monitoring), employer_config (I — Section A identity: DTI/PAYE/UIF/EE ref, SETA classification, EAP choice), **remuneration_record (R — per-employee annualised fixed + variable remuneration imported from SAP payroll; required to generate EEA4)** | Sprint 13 (spec: `EEA-Form-Spec-Notes.md`) |

## Open data questions

1. ~~Exact EEA2/EEA4 field layout~~ → **Resolved 2026-08-12**: forms received and analysed; see `EEA-Form-Spec-Notes.md`. Still outstanding: the DEL *online portal* upload format (the forms define content, not the electronic file schema) — confirm at first submission rehearsal.
2. Which spreadsheets/SAP tables hold current demographics, and their race/gender coding schemes (mapping tables needed for import) (A2 — sources named, detail inventory outstanding).
3. ~~Foreign-national treatment~~ → **Resolved**: FN are separate Male/Female columns, not raced; race applies to citizens only. Captured via `citizenship_status`.
4. Whether Sentech grades map 1:1 to EEA occupational levels or need a mapping review with HR (A2).
5. **New:** SAP payroll extract feasibility and format for `remuneration_record` (fixed vs. variable split per EEA4 definitions) — folds into action A10.
