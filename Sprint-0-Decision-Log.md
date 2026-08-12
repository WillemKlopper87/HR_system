# Sprint 0 — Decision Log & Open Actions

**Sprint goal:** Confirm decisions, define data dictionary, stand up scaffolding.
**Started:** 2026-08-12

## Decisions ratified

| # | Decision | Choice | Ref | Date |
|---|---|---|---|---|
| 1 | Backend framework | **Django 5 + Django REST Framework** | ADR-001 | 2026-08-12 |
| 2 | Assessments approach | **Integrate 3rd-party provider** behind adapter layer | ADR-003 | 2026-08-12 |
| 3 | Build/test data | **Synthetic dataset** (~600 employees, SA demographic distribution); real data only at migration rehearsal, under POPIA controls | — | 2026-08-12 |
| 4 | Code location | **`HR_system/hcm/`** — app scaffold lives alongside the project docs | — | 2026-08-12 |

## Decisions proposed, awaiting sign-off

| # | Decision | Proposed | Ref | Owner / needed from |
|---|---|---|---|---|
| 5 | History/versioning pattern | Effective-dated rows + django-simple-history | ADR-002 | Tech lead (default-accept unless objection by Sprint 1 start) |
| 6 | Authentication | OIDC SSO via Microsoft Entra ID | ADR-004 | Sentech IT — confirm app registration is possible |
| 7 | Hosting | Docker Compose, single node, dev/staging/prod | ADR-005 | Sentech IT — on-prem VM vs. Azure |
| 8 | Pay-data authority | SAP/payroll masters actual pay; HCM masters bands + proposals | ADR-006 | Payroll/SAP team |

## Open actions (Sprint 0 exit blockers) — statuses updated 2026-08-12

| # | Action | Owner | Status |
|---|---|---|---|
| A1 | Confirm legal/country scope and EE designated-employer status | HR / Legal | ✅ **Resolved:** South Africa; government / State-Owned Company. As an organ of state, Sentech is a **designated employer regardless of headcount**; EEA reports are authorised by the **Accounting Officer** (PFMA) |
| A2 | Identify existing systems/spreadsheets holding recruitment, performance, learning, comp, EE data | HR | ◐ **Partially resolved:** sources are **spreadsheets + SAP** (used as a CRM-type employee data store). Outstanding: itemise which spreadsheets/SAP tables hold what, and their coding schemes (data dictionary open questions 2 & 4) |
| A3 | Obtain latest official EEA2/EEA4 form specs | EE manager | ✅ **Resolved:** `EEA2 Form.docx` + `EEA4 Form.docx` received (amended forms, 2025–2030 sector-target period) and analysed → `EEA-Form-Spec-Notes.md`. Only the DEL online portal's electronic upload schema remains to confirm at submission rehearsal |
| A4 | Shortlist 1–2 assessment providers with documented APIs | HR + IT | Deferred — greenfield decision; not needed until Sprint 12 planning. Adapter design (ADR-003) is provider-agnostic, so this doesn't block anything before then |
| A5 | Decide parallel vs. sequential build for talent tracks (Sprints 4–12) | Project sponsor | Open — **sequential assumed** for planning (see explanation in log below); revisit only if additional build capacity becomes available |
| A6 | Decide leave management in/out of scope | HR | ✅ **Resolved: out of scope** — leave is managed in SAP. Roadmap note: possible read-only sync from SAP payroll later, if access is granted (extends ADR-006 interface) |
| A7 | Confirm NFR targets (`Architecture-Design.md` §9) | Sponsor + IT | Open — proposed targets stand as working assumptions until revised (see explanation in log below) |
| A8 | Locate original PRD / Project Plan / Tech Architecture docs, or ratify sprint plan as baseline | Project sponsor | ✅ **Resolved by decision:** no separate PRD exists. The sprint plan + gap analysis + architecture design in this folder **are the requirements baseline**, evolving with user requirements (per A9 approach) |
| A9 | Publish signed-off out-of-scope list | Project sponsor | ✅ **Resolved as policy:** scope is **open/rolling** — build and refine per emerging user requirements. The out-of-scope list below stands as the *current* boundary and is revised as requirements land, rather than fixed by one-time sign-off |
| A10 | Draft payroll/SAP interface contract (direction per ADR-006) | SAP team + tech lead | Open — **priority raised**: the received EEA4 form requires per-employee annualised remuneration (fixed + variable), so a SAP payroll extract is a hard dependency for EE reporting (Sprints 13–14), not just the comp module. See `EEA-Form-Spec-Notes.md` §Consequences |

## Current out-of-scope list (living document per A9 — revised as requirements land)

Out of scope for v1 as of 2026-08-12:

- Payroll processing (integration only, per ADR-006)
- Leave / time & attendance — **managed in SAP (A6 resolved)**; possible read-only sync later
- Disciplinary / ER case management
- Succession planning & talent matrices
- Native mobile apps (responsive web only)
- AD account provisioning from hire events (identity lifecycle — roadmap)
- B-BBEE scorecard generation (data will support it; reports later)

## Sprint 0 deliverables status

| Deliverable | Location | Status |
|---|---|---|
| Decision log | this file | ✅ |
| ADR records | `adr/` | ✅ |
| Data dictionary draft | `Data-Dictionary.md` | ✅ Draft — pending A2/A3 refinement + sign-off |
| RBAC role definitions | `RBAC-Roles.md` | ✅ Draft |
| App scaffold (Django + React + Compose + CI) | `hcm/` | ✅ |
| Environment provisioning (staging Postgres) | — | Open — depends on ADR-005 sign-off (A7/IT) |
