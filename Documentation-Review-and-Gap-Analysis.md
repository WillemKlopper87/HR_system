# HCM System — Documentation Review & Gap Analysis

**Date:** 2026-08-12
**Scope reviewed:** `Sprint-Plan-HCM-System.md` (the only document currently in `HR_system/`)
**Companion document:** `Architecture-Design.md` (proposed technical architecture addressing the gaps below)

---

## 1. Documentation Review

### 1.1 What exists

| Document | Status |
|---|---|
| Sprint Plan (`Sprint-Plan-HCM-System.md`) | ✅ Present |
| PRD | ❌ Missing — referenced by the sprint plan but not in the folder |
| Project Plan | ❌ Missing — referenced but not in the folder |
| Technical Architecture / ADRs | ❌ Missing — referenced but not in the folder |
| Data dictionary | ❌ Not yet produced (Sprint 0 deliverable) |

The sprint plan opens with *"Consolidates the PRD, Project Plan, and Technical Architecture"* — but those three source documents are not present. The sprint plan is therefore currently **unverifiable against its own requirements baseline**. If the source documents exist elsewhere (email, SharePoint, another repo), they should be copied into this folder; if they don't, the sprint plan is effectively the de-facto PRD and should be treated (and hardened) as such.

### 1.2 Strengths of the sprint plan

The document is genuinely good in several ways worth preserving:

- **Correct dependency ordering.** Core HR + RBAC/audit before everything else, with a hard gate after Sprint 3, is the right call — every downstream module hangs off `employees`.
- **Shared RBAC + audit as a foundation, not a per-module afterthought.** This is the single most common failure mode in HR systems and the plan explicitly forbids it ("do not build per-module access control").
- **Effective-dated history from Sprint 1.** As-at reporting is required for EE submissions; retrofitting temporal data is painful. Building it first is correct.
- **Hire → employee record automation** (no re-entry) is called out with an acceptance criterion.
- **Assessments handled as an integrate-vs-build decision** with a sensible default (integrate) and an explicit "don't estimate an internal build without psychometrician input" guard.
- **Acceptance criteria on most sprints**, written in given/when/then form — agent-executable.
- **Sensitive-field handling stated as a hard constraint**, not a judgment call.

### 1.3 Weaknesses of the sprint plan itself

1. **Tech stack still undecided** ("Django/Laravel/Node") yet Sprint 0 says "base app scaffold (chosen framework)". There is no ADR and no decision owner. This blocks Sprint 0. → Resolved as **ADR-001** in `Architecture-Design.md` (recommendation: Django).
2. **No non-functional requirements anywhere.** No user counts, concurrency, availability target, response-time budget, data volumes. Impossible to size infrastructure or judge "done".
3. **No authentication story.** RBAC is specified in detail but *who logs in and how* is never stated. Sentech will almost certainly require corporate SSO (AD/Entra ID).
4. **No deployment/hosting decision.** Dev/staging PostgreSQL is mentioned; production, backup, DR, and on-prem-vs-cloud are absent.
5. **Employee lifecycle is only half-modelled.** Hire is automated; **promotion, transfer, termination/offboarding are missing entirely**. Terminations are mandatory input to EEA2 (workforce movement section) — this is a functional *and* compliance gap.
6. **Self-ID/consent arrives too late.** Employee self-service (including the self-ID consent flow) is Sprint 15, but EE reporting (Sprints 13–14) depends on demographic data quality. HR-captured demographics without employee self-ID/verification will produce a weak EEA2 dataset.
7. **Testing is back-loaded.** The RBAC test suite (Sprint 2) is the only continuous quality mechanism; everything else waits for Sprints 16–17. Each module sprint should carry its own regression additions.
8. **The parallelization claim is optimistic.** Compressing Sprints 4–12 (~18 weeks of work) into 6–8 weeks implies 3+ parallel streams plus integration overhead, against a single shared data model. Feasible, but only with real staffing — the plan doesn't define team size or roles.
9. **No risk register, no change-control process** beyond the ADR note.

---

## 2. Gap Analysis

Legend: **P1** = blocks build or creates legal exposure; **P2** = should be resolved before the affected sprint; **P3** = improvement / backlog.

### 2.1 Documentation gaps

| # | Gap | Priority | Recommended action |
|---|---|---|---|
| D1 | PRD, Project Plan, Technical Architecture referenced but absent | P1 | Locate and commit them, or ratify the sprint plan as the requirements baseline |
| D2 | No architecture document / ADRs | P1 | ✅ Addressed by `Architecture-Design.md` in this folder |
| D3 | No data dictionary | P1 | Sprint 0 deliverable — template proposed in Architecture doc §5 |
| D4 | No NFR specification | P1 | Proposed targets in Architecture doc §9; confirm with stakeholders |
| D5 | No risk register | P2 | Seed from §3 below |

### 2.2 Functional scope gaps (for a "full-scope HCM")

| # | Gap | Priority | Notes |
|---|---|---|---|
| F1 | **Termination/offboarding & lifecycle events** (promotion, transfer, contract change) | P1 | Required for EEA2 workforce-movement reporting; extend Sprint 1 data model + add workflow in Sprint 3 |
| F2 | **Leave / absence management** | P2 | BCEA-governed (annual, sick, family responsibility). Either in scope as a module or explicitly out of scope with the system of record named |
| F3 | **Payroll** | P1 (as a decision) | Almost certainly out of scope to *build* — but the integration boundary must be designed (see I1). Pay bands without payroll linkage drift immediately |
| F4 | Onboarding workflow (checklists, document collection) | P3 | Natural extension of the hire event |
| F5 | Time & attendance | P3 | Confirm out of scope |
| F6 | Disciplinary / employee-relations case tracking | P3 | Often requested post-launch; keep out of v1 but note in roadmap |
| F7 | Succession planning / talent matrix | P3 | Builds on Performance + L&D data; roadmap item |
| F8 | Document management (contracts, IDs, certificates) | P2 | Needed by recruitment (offer letters) and core HR; decide store-in-app vs. link-to-SharePoint |
| F9 | Notifications & approval routing engine | P2 | Comp reviews, EE sign-off, review cycles all assume approvals/notifications exist — no sprint builds them. Add to Sprint 3 as shared infrastructure |

### 2.3 Compliance gaps (South Africa)

| # | Gap | Priority | Notes |
|---|---|---|---|
| C1 | **POPIA treatment is implicit, not designed.** Race, health/disability data are *special personal information* (POPIA s26–27) | P1 | Consent capture exists in the plan, but missing: lawful-basis mapping (EE reporting is a legal obligation — consent is not the only basis), data-subject access/correction/deletion rights, retention & deletion schedule, Information Officer sign-off, breach-notification procedure. Architecture doc §8 covers controls |
| C2 | **Skills Development Act reporting (WSP/ATR to SETA, due 30 April annually)** absent from L&D sprints | P1 | The L&D module captures exactly this data — add WSP/ATR export to Sprints 8–9 or it will be rebuilt in spreadsheets |
| C3 | EEA2/EEA4 spec volatility | P2 | DEL revises forms/portal periodically; the Sprint 0 task gets *current* specs but the validation engine should treat the field layout as versioned configuration, not code |
| C4 | B-BBEE reporting (employment-equity + skills-development elements) | P3 | Same underlying data; add as report outputs later — no new data capture needed if C2 is done |
| C5 | Audit-log retention, immutability and AGSA-auditability (Sentech is a SOC under PFMA) | P2 | Specify append-only storage + retention period; Architecture doc §7 |
| C6 | Aggregation privacy on dashboards (small-cell disclosure — e.g., "disabled female employees in Dept X, Level Y" = 1 person) | P2 | Add k-anonymity/small-cell suppression rule to the Sprint 3 dashboard and all EE dashboards |

### 2.4 Technical / NFR gaps

| # | Gap | Priority | Notes |
|---|---|---|---|
| T1 | Framework decision (Django vs. Laravel vs. Node) | P1 | ADR-001 in Architecture doc — recommendation: **Django + DRF** |
| T2 | Authentication / SSO | P1 | ADR-004: OIDC against Microsoft Entra ID (Sentech is an M365 shop — this workspace itself lives in OneDrive) |
| T3 | History/versioning implementation pattern unchosen | P1 | ADR-002: effective-dated rows for org-truth entities + `django-simple-history` for audit trail; details in Architecture doc §5 |
| T4 | Production environment, backup/DR, environments beyond dev/staging | P1 | ADR-005; Architecture doc §10 |
| T5 | API design standard (versioning, pagination, error format) | P2 | Architecture doc §6 |
| T6 | File/object storage for imports, exports, generated EEA reports | P2 | Architecture doc §10 |
| T7 | Background-job infrastructure (report generation, bulk import, webhooks) | P2 | Celery/worker pattern; Architecture doc §4 |
| T8 | Observability (logging, metrics, error tracking) | P2 | Architecture doc §10 |

### 2.5 Integration gaps

| # | Gap | Priority | Notes |
|---|---|---|---|
| I1 | **Payroll/ERP integration undefined.** A `sap-finance-platform` project exists in this same workspace — SAP is in the Sentech landscape | P1 | Decide direction of authority: is HCM or SAP (or a payroll bureau) the master for pay data? Design the interface contract in Sprint 0; build in a dedicated sprint (proposed Sprint 12b) |
| I2 | Email/notification delivery channel (SMTP relay vs. Microsoft Graph) | P2 | Pairs with F9 |
| I3 | Identity lifecycle (joiner/leaver sync with AD — does a hire in HCM trigger account provisioning?) | P3 | Out of scope for v1, but name it |
| I4 | Assessment-provider webhook security (signature verification, replay protection) | P2 | Add to Sprint 12 acceptance criteria |

### 2.6 Delivery-process gaps

| # | Gap | Priority | Notes |
|---|---|---|---|
| P1a | No team/roles definition; parallelization math assumes staff that isn't specified | P2 | Define streams before invoking the 20–24-week timeline |
| P2a | UAT only at the end; no per-phase stakeholder demo cadence | P2 | Add demo + sign-off to each phase exit |
| P3a | No data-migration plan beyond generic bulk import (source systems unnamed) | P2 | Sprint 0 task exists to *identify* sources; add a migration rehearsal before go-live |

---

## 3. Top risks (seed for the risk register)

1. **EE reporting built on unverified demographic data** — self-ID too late in the plan → wrong EEA2 numbers submitted to DEL. *Mitigation:* move self-ID/consent flow earlier (see §4).
2. **POPIA special-personal-information handling challenged** (internal audit or Information Regulator) → *Mitigation:* lawful-basis register + the RBAC/audit layer already planned + retention schedule.
3. **Pay-band data drifts from payroll reality** → comp module loses credibility. *Mitigation:* decide I1 before Sprint 10.
4. **Scope creep from missing modules** (leave, payroll expectations) discovered mid-build. *Mitigation:* publish an explicit out-of-scope list at Sprint 0 exit.
5. **Single-stream timeline (36 weeks) misses an EE reporting deadline** (annual DEL submission window). *Mitigation:* schedule Sprints 13–14 to land ≥2 months before the next submission deadline, even if that means re-ordering.

---

## 4. Recommended amendments to the sprint plan

Concrete, minimal changes — the plan's structure survives; these slot in:

| Change | Where | Why |
|---|---|---|
| Add **lifecycle events** (terminate, promote, transfer) to the data model and admin UI | Sprint 1 & 3 | EEA2 workforce movement; F1 |
| Add **notification + approval-workflow primitives** as shared infrastructure | Sprint 3 | Every later module assumes them; F9 |
| Pull the **self-ID & consent flow forward** into a "Sprint 3.5" mini-sprint (or into Sprint 3) and treat full ESS (Sprint 15) as its extension | After Sprint 3 gate | Data quality for EE reporting; risk #1 |
| Add **WSP/ATR (SETA) export** tasks | Sprints 8–9 | C2 — same data, statutory deadline |
| Insert **Sprint 12b — Payroll/ERP interface** (direction-of-authority decision made in Sprint 0) | After Sprint 12 | I1 |
| Add **small-cell suppression** acceptance criterion to every demographic dashboard | Sprints 3, 13–14 | C6 |
| Add "module regression tests extend the Sprint 2 baseline suite" as a standing task in every sprint | All | Testing back-load |
| Add Sprint 0 decisions: **SSO provider, hosting target, payroll master-data direction, leave in/out of scope** | Sprint 0 | T2, T4, I1, F2 |

With these amendments the sequential estimate moves from ~18 to **~20 sprints (~40 weeks)**; parallelized, roughly **24–28 weeks** with 2–3 streams.
