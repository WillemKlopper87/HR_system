[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

## Sprint 0 — Discovery & Environment Setup
**Goal:** Confirm decisions, define data dictionary, stand up scaffolding.
**Status: mostly done** (2026-08-12) — 7 of 10 tasks confirmed resolved against `Sprint-0-Decision-Log.md` (the authoritative decision record for this sprint). Still open: identifying which specific spreadsheets/SAP tables hold what (A2 — partially resolved, sources identified as "spreadsheets + SAP" but not itemised); the assessment-provider shortlist (A4 — deferred, "not needed until Sprint 12 planning", and still open as of Sprint 12c per that sprint's own notes); and a formal parallel-vs-sequential ruling (A5 — left "Open" in the decision log even though "sequential" was the assumed default and is what every sprint since has actually run as, confirmed by git history being one linear commit stream throughout).

**Tasks:**
- [x] Confirm legal/country scope (SA-only vs. broader) and EE designated-employer status — `Sprint-0-Decision-Log.md` A1: South Africa; organ of state, designated employer regardless of headcount; EEA reports authorised by the Accounting Officer (PFMA)
- [ ] Identify existing systems/spreadsheets holding recruitment, performance, learning, compensation, EE data — A2 partially resolved only: sources identified as "spreadsheets + SAP" but the specific spreadsheets/tables and coding schemes were never itemised
- [x] Obtain latest official EEA2/EEA4 form specs and DEL submission file format — A3: `EEA2 Form.docx` + `EEA4 Form.docx` received and analysed into `EEA-Form-Spec-Notes.md`; only the DEL portal's electronic upload schema remains open, deferred to submission rehearsal
- [x] Draft cross-module data dictionary (fields, types, sensitivity classification per field) — `Data-Dictionary.md` (decision log: "✅ Draft — pending A2/A3 refinement + sign-off")
- [x] Decide: real vs. synthetic data for initial build/testing — Decision #3: synthetic dataset (~600 employees, SA demographic distribution); real data only at migration rehearsal under POPIA controls
- [x] Decide: Assessments — integrate 3rd-party provider vs. build internal (default recommendation: integrate; see Architecture) — Decision #2 / ADR-003: integrate behind an adapter layer
- [ ] Shortlist 1–2 assessment providers with documented APIs if integrating — A4: explicitly deferred, not needed until Sprint 12 planning; confirmed still open in Sprint 12c's own notes ("no vendor is under contract")
- [ ] Decide: parallel or sequential build for talent tracks (affects sprint numbering below) — A5: left formally "Open" in the decision log; "sequential" was the assumed default for planning and is what every sprint since has actually run as (one linear commit stream), but never formally ratified
- [x] Set up repo, CI/CD pipeline, PostgreSQL instance (dev/staging), base app scaffold (chosen framework) — repo/CI/dev-Postgres/scaffold all confirmed live and in continuous use (`hcm-ci.yml`, docker-compose `db` service); the decision log separately lists *staging* Postgres provisioning as still open pending ADR-005/IT hosting sign-off, which hasn't blocked any sprint since
- [x] Define role list for RBAC (e.g., HR admin, EE manager, line manager, employee, recruiter, comp manager, auditor) — `RBAC-Roles.md`, seeded as the 8-role grant matrix in Sprint 2 (`rbac_audit` migration `0002_seed_roles`)

**Exit criteria:** Signed-off data dictionary; environment provisioned; open decisions above resolved or explicitly deferred with an owner.

