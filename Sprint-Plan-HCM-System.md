# Sprint Plan: Full-Scope HCM System (Agent-Ready)

**Purpose:** Consolidates the PRD, Project Plan, and Technical Architecture into a single sequential, sprint-phased backlog an agent can execute against. Sprints are 2 weeks each, sequential by default (single build stream). If multiple parallel agents/engineers are available, Sprints 4–12 (the talent tracks) can be split across them per the Project Plan's Phase 2 parallelization note.

**Architecture baseline (do not deviate without a new ADR):** Modular monolith. React frontend, single backend (Django/Laravel/Node), single PostgreSQL database, one `employees` table as source of truth, one shared RBAC + audit-logging layer used by every module.

**Non-negotiable sequencing rule:** Sprints 1–3 (Core HR + RBAC/audit foundation) must complete before any other module starts. Every later module's data model has a foreign key back to `employees`.

**How this file is organized (reorganized 2026-08-20):** this used to be one 580+ line document carrying every sprint's full status block inline. It's now an index — each row below is one line of status with a link into `docs/sprints/` for the full implementation notes, design-tension callouts, and verification counts. Nothing was dropped in the split; every task/checkbox that existed before still exists in its linked file, plus this pass reconciled Sprint 0's checkboxes (all ten were still `[ ]` despite most being long resolved) and a couple of other stale ones found along the way — see each file's own history for what changed and why. **`ROADMAP-2026-08.md` is the authoritative sequencing/dependency source** for everything from H1 onward (the 2026-08-18 hardening split, KPI contracting, and C1–C7 capabilities) — read it alongside this index for *why* things are ordered the way they are, not just *what* is done.

---

## Original numbered plan (Sprints 0–17)

| Sprint | Goal | Status |
|---|---|---|
| [Sprint 0 — Discovery & Environment Setup](docs/sprints/sprint-00-discovery-setup.md) | Confirm decisions, define data dictionary, stand up scaffolding | Mostly done (2026-08-12) — 7/10 tasks confirmed against the decision log; spreadsheet/table inventory (A2), assessment-provider shortlist (A4), and a formal parallel-vs-sequential ruling (A5) still open |
| [Sprint 1 — Core HR Data Model](docs/sprints/sprint-01-core-hr-data-model.md) | Single source-of-truth employee table with history support | Done (2026-08-12) |
| [Sprint 2 — RBAC & Audit Foundation](docs/sprints/sprint-02-rbac-audit-foundation.md) | Shared access-control and audit layer every later module reuses | Done (2026-08-12) |
| [Sprint 3 — Core HR Dashboards & Admin UI](docs/sprints/sprint-03-core-hr-dashboards-admin-ui.md) | HR admins can manage/view core data; unblocks downstream modules | Done (2026-08-12) — hard gate passed |
| [Sprint 4–5 — Recruitment / ATS](docs/sprints/sprint-04-05-recruitment-ats.md) | Requisition-to-hire pipeline feeding directly into `employees` | Done (2026-08-12) |
| [Sprint 6–7 — Performance Management](docs/sprints/sprint-06-07-performance-management.md) | Goal-setting and structured review cycles tied to `employees` | Done (2026-08-12) |
| [Sprint 8–9 — Learning & Development](docs/sprints/sprint-08-09-learning-development.md) | Skills/certifications record per employee, org-wide visibility | Done (2026-08-13) |
| [Sprint 10–11 — Compensation & Benefits](docs/sprints/sprint-10-11-compensation-benefits.md) | Pay bands and a controlled compensation review workflow | Done (2026-08-13) |
| [Sprint 12 — Assessments & Psychometric Testing](docs/sprints/sprint-12-assessments-psychometric-testing.md) | Provider-agnostic assessment integration layer | Done (2026-08-13) — optional AI summarization task explicitly out of scope |
| [Sprint 12c — Workforce Integrity (unplanned)](docs/sprints/sprint-12c-workforce-integrity.md) | Ghost-employee mitigation via biometric liveness + office-attendance check | Done (2026-08-13) |
| [Sprint 13–14 — Equity / EE Reporting](docs/sprints/sprint-13-14-equity-ee-reporting.md) | Draft EEA2/EEA4 generation from Recruitment/Performance/Compensation data | Done (2026-08-13) |
| [Sprint 15 — Employee Self-Service](docs/sprints/sprint-15-employee-self-service.md) | Employees manage their own profile/consent/benefits/learning requests | Done (2026-08-13) |
| [Policy Section (unplanned, ADR-008)](docs/sprints/policy-section-hr-policy-library.md) | HR policy document library with per-employee acknowledgment tracking | Done (2026-08-13) — embeddings/chatbot/abuse-prevention design explicitly deferred, no LLM wiring exists |
| [Step-Up Authentication for Payroll Data (unplanned, ADR-009)](docs/sprints/step-up-authentication-payroll.md) | Step-up MFA + justification reason required to view Restricted-tier payroll data | Done (2026-08-13) |
| [Sprint 16–17 — Hardening & UAT](docs/sprints/sprint-16-17-hardening-uat-superseded.md) | Production-pilot readiness across all modules | **Superseded** — never executed as originally written; replaced by H1–H3 + UAT-1 below |

---

## Backlog additions 2026-08-18 — hardening split, KPI contracting, capabilities

*(Sequencing, dependencies and reasoning live in `ROADMAP-2026-08.md`; the review that produced them in
`NEXT_AGENT_BRIEF.md`; the KPI design in `docs/superpowers/specs/2026-08-18-kpi-contracting-design.md`, ADR-010/011.
Sprint 16–17 above is superseded by H1–H3 + UAT-1 below.)*

| Sprint | Scope | Status |
|---|---|---|
| [H1 — Platform foundations](docs/sprints/h1-platform-foundations.md) | Celery/beat, throttling, Postgres-in-CI, lock file, 401 handling, compose frontend service, ADRs | Done (2026-08-18) |
| [H2 — Test harness + frontend consolidation](docs/sprints/h2-test-harness-frontend-consolidation.md) | Playwright e2e suite, shared fetch hooks, golden RBAC matrix, module-boundary test, upload sniffing | Done (2026-08-18) |
| [X0 — Collab platform integration surface](docs/sprints/x0-collab-integration-surface.md) | Service-account auth, `WorkItem.external_ref`, announcements (other repo) | Done (2026-08-18, collab repo `23d4f05`) |
| [PC-0 — HR → collab adapter (ADR-011)](docs/sprints/pc0-collab-adapter.md) | `integrations` app: collab client, identity mapping, contract tests | Done (2026-08-18) |
| [PC-1 — Performance contracting (ADR-010)](docs/sprints/pc1-performance-contracting.md) | Periods, templates, agreements, signing, delegation, reminders | Done (2026-08-18, `6bcb396`) |
| [PC-2 — Reviews, evidence, scoring](docs/sprints/pc2-reviews-evidence-scoring.md) | Q2/Q4 stages, evidence items, scoring, legacy review bridge | Done (2026-08-19, `96c0c9c`) |
| [PC-3 — Archive, dashboards, outcomes](docs/sprints/pc3-archive-dashboards-outcomes.md) | Period archive, rating distribution, `ImprovementPlan` stub | Done (2026-08-19, `794681e`) |
| [H3 — Cross-cutting HR platform](docs/sprints/h3-cross-cutting-platform.md) | Notifications, audit-log viewer, ops/observability, OpenAPI, data-quality registry, EEA validation, docs split | In progress (2026-08-19/20) — all 6 functional slices + this docs-split done; only the `api/types.ts` swap remains |
| [UAT-1 — Rolling gate](docs/sprints/backlog-uat1-and-c2-c7.md) | Walkthrough script, stakeholder UAT, security/compliance sign-off | Not started — needs people, blocked on H3 + PC-3 |
| [C1 — Establishment & lifecycle](docs/sprints/c1-establishment-lifecycle.md) | `Position`/establishment (part 1); contract/probation reminders + onboarding-offboarding checklists (parts 2–3) | Part 1 of 3 done (2026-08-19, `b2ad0c0`); parts 2–3 not started, need their own spec |
| [C2 — Employee documents & POPIA rights](docs/sprints/backlog-uat1-and-c2-c7.md) | `EmployeeDocument`, dependants/emergency contacts, data-subject export/erasure | Not started |
| [C3 — Identity & integrations](docs/sprints/backlog-uat1-and-c2-c7.md) | OIDC/Entra SSO, SAP payroll read-only pull, `recruitment.Offer` field-level step-up | Not started |
| [C4 — Generic delegation & approvals](docs/sprints/backlog-uat1-and-c2-c7.md) | Generalise `SigningDelegation` → `Delegation(scope)`; approvals inbox | Not started |
| [C5 — Labour relations](docs/sprints/backlog-uat1-and-c2-c7.md) | Disciplinary & grievance case management | Not started |
| [C6 — Talent depth](docs/sprints/backlog-uat1-and-c2-c7.md) | Succession, interview scheduling, calibration/360, training compliance, etc. (per demand) | Not started |
| [C7 — UX / NFR](docs/sprints/backlog-uat1-and-c2-c7.md) | Responsive + accessibility pass, server-side pagination, bulk import/export, report builder | Not started |

*(UAT-1 and C2–C7 share one file, `docs/sprints/backlog-uat1-and-c2-c7.md`, since none of them have started yet — each is a short scope stub, not a status block. C1 has its own file because part 1 is real, shipped work.)*

---

## Summary Timeline
*(Original numbered plan, Sprints 0–17, as sequenced before the 2026-08-18 backlog additions above superseded 16–17.)*

| Sprints | Module | Duration |
|---|---|---|
| 0 | Discovery & Setup | 1 sprint (2 wks) |
| 1–3 | Core HR + RBAC/Audit (hard gate) | 3 sprints (6 wks) |
| 4–5 | Recruitment/ATS | 2 sprints (4 wks) |
| 6–7 | Performance Management | 2 sprints (4 wks) |
| 8–9 | Learning & Development | 2 sprints (4 wks) |
| 10–11 | Compensation & Benefits | 2 sprints (4 wks) |
| 12 | Assessments (integration path) | 1 sprint (2 wks) |
| 13–14 | Equity/EE Reporting | 2 sprints (4 wks) |
| 15 | Employee Self-Service | 1 sprint (2 wks) |
| 16–17 | Hardening & UAT | 2 sprints (4 wks) |
| **Total (sequential)** | | **~18 sprints / 36 weeks** |

If Sprints 4–12 (talent tracks + assessments) run across parallel workstreams instead, that block compresses from ~22 weeks to as little as ~6–8 weeks — reducing total timeline to roughly **20–24 weeks**, per the original Project Plan's parallelization note.

## Notes for the Executing Agent
- Do not start any module before its dependencies (per sprint order above) are complete — every table has an FK to `employees`.
- Reuse the Sprint 2 RBAC/audit implementation everywhere; do not build per-module access control.
- Flag any deviation from the modular-monolith architecture (e.g., wanting to split a module into a separate service) back to a human before proceeding — that's an ADR-level decision, not a sprint-level one.
- Sensitive fields (race, gender, disability, pay, performance ratings, assessment results) must always route through the Sprint 2 RBAC layer — treat this as a hard constraint, not a per-feature judgment call.

## Maintaining this file
- Detailed sprint work (implementation notes, design tensions, verification counts) belongs in its own `docs/sprints/<slug>.md` file, not back in this index — that sprawl is exactly what the 2026-08-20 split fixed.
- When a sprint/capability finishes, update its `docs/sprints/*.md` file (status line, checkboxes, verification) and update this file's one-line status cell + link. A brand-new unplanned addition (like 12c/Policy/Step-up before it) gets its own new `docs/sprints/*.md` file and a new row in the appropriate table above.
- `ROADMAP-2026-08.md` owns sequencing/dependency reasoning for H1 onward; don't duplicate that reasoning here — link to it.
