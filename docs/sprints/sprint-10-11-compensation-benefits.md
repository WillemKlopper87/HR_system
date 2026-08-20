[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

## Sprint 10–11 — Compensation & Benefits
**Goal:** Pay bands and a controlled compensation review workflow.
**Status: done** (2026-08-13) — see `hcm/backend/compensation/` (new app) and `PayBandsPage.tsx` / `CompProposalsPage.tsx` / `BenefitsPage.tsx` in the frontend. Verified end-to-end in a real browser: comp manager defines a pay band, proposes an out-of-band raise (auto-flagged), a *different* user (hr_admin) approves it with an override reason, and a line manager/plain employee are confirmed shut out of the entire module (nav hidden, direct URL redirected, API 403).

**Tasks:**
- [x] Pay band definitions by job level (with history/versioning per Sprint 1 pattern) — `PayBand` (Restricted-tier, `valid_from`/`valid_to` + `PayBandQuerySet.as_at()/.current()`, the same effective-dated pattern as `core_hr.EmployeeVersion`); DB-level `CheckConstraint`s enforce `min ≤ mid ≤ max` and `valid_to > valid_from`
- [x] Compensation review workflow: manager proposes → approver reviews → sign-off — `CompProposal` + `compensation/services.py` (`propose_compensation_change` → `approve_proposal`/`reject_proposal`); segregation of duties enforced server-side (the proposer can't also approve — same standing rule as `recruitment.Offer.approve()`), not just hidden in the UI
- [x] Basic benefits election tracking — `Benefit` (catalog) + `BenefitsElection` (`UniqueConstraint(employee, benefit)`); recording-only this sprint, employee self-service is Sprint 15's explicit task
- [x] Pay-data visibility restricted to comp manager/HR admin roles only (strict RBAC) — `IsCompManagerOrHRAdmin` gates the *entire* module (pay bands and the benefits catalog included, not just individual salary figures), per the acceptance criterion's literal wording

**A real design tension, resolved the same way as recruitment's offer-pay exception and performance's Review/Feedback:** RBAC-Roles.md's comp_manager row-scope is "all," but comp_manager's *generic* Sensitive-tier grant is aggregate-only (S: closed) and its Restricted-tier grant is the only one in the whole role matrix with **write** access. Rather than force that mismatch through the generic `TieredModelSerializer`/`can_access_tier_for_target` path, the whole compensation module bypasses it and gates purely on role via `IsCompManagerOrHRAdmin` — plain `ModelSerializer`s throughout. `CompProposal.current_job_grade`/`status`/`requires_override` are also deliberately server-computed and marked `read_only_fields` — a client can't forge an already-approved proposal or swap the pay band it's checked against.

**Acceptance criteria:**
- [x] Compensation adjustments outside a defined pay band trigger a flag/require override approval. — `evaluate_requires_override()` checks the proposed salary against the employee's *current* pay band at propose time (missing grade or missing band is treated conservatively as requiring override, not silently waved through); `approve_proposal()` refuses to approve a flagged proposal without an `override_reason`
- [x] Pay data is not visible to line managers unless explicitly granted. — verified both ways: `compensation/test_api.py::ModuleWidePermissionTests` (API) and a live browser session (nav hidden, direct `/pay-bands` URL redirected to `/employees`)

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 166/166 tests project-wide (134 prior + 32 new). Frontend `tsc -b && vite build` and `oxlint` both pass. `seed_demo_data.py` extended with a `compmanager`/`compmanager123` demo login, pay bands per job grade (one grade carries an expired + current band to show the effective-dated pattern), and comp proposals spanning every workflow state (pending, approved in-band, approved out-of-band with an override reason, rejected).

