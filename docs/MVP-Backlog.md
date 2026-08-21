# MVP Backlog — unplanned gaps & the demoable-lifecycle reframing

**Created 2026-08-20.** Companion to `ROADMAP-2026-08.md`, which sequences by technical dependency.
This document sequences by **what can be demonstrated to a person**, and captures every capability that
currently has *no home* on the C1–C7 backlog.

Two distinct things live here:

- **Part A** — capabilities with no plan at all. Raised because a survey of mature HRIS/HCM practice
  (the "Gap Survey") listed them and the C1–C7 backlog has no entry for them either way.
- **Part B** — the employee-lifecycle journey, and what blocks demoing it end to end.

---

## Part A — No home on the C1–C7 backlog

### A1. Core modules

| # | Capability | Status | Note |
|---|---|---|---|
| 1 | **HR helpdesk / case management** | Unplanned | Ticketing, query routing, SLAs. Would pair naturally with C4's approvals inbox. |
| 2 | **Engagement / pulse surveys / eNPS** | Unplanned | No module, no backlog entry. Doesn't touch compliance, payroll integrity, or establishment control — the three themes this system is organised around. |
| 3 | **Org chart visualisation** | ✅ Built (HR side) — staff-facing view assigned to collab | `/org-chart` shipped 2026-08-20: collapsible tree over `EmployeeVersion.manager`, search with ancestor reveal, cycle-safe by construction. **Role-gated** — see the decision below. |

#### Decision (2026-08-20): who sees the org chart, and where it lives

The HR-system chart is gated to roles that can see a meaningful tree (`hr_admin`, `line_manager`,
`auditor`, `ee_manager`, `recruiter`, `comp_manager`, `accounting_officer`). A plain `employee` has
`row_scope=self`, so they would see a chart containing only themselves.

Opening it to everyone *inside HR_system* was considered and rejected. `manager` is **INTERNAL** tier
(`rbac_audit/tiers.py`), so a company-wide tree would mean either declassifying that field or carving a
bypass around row-scoping — in a system whose stated differentiator is exactly that access model. Neither
is worth a convenience feature.

**User decision:** every staff member *should* be able to see the org chart, but that view belongs on the
**collab platform**, not here — so it doesn't disturb an access model already built and reviewed. Today
collab carries only a high-level picture, not granular reporting lines; the full picture stays with HR.

Consequences for whoever picks that up (cross-repo, not HR_system work):

- HR_system remains **system of record** for reporting lines. Collab renders; it does not own.
- `integrations/collab.py` is deliberately **outbound-only** and, per its own docstring, "never reads back
  state that would drive HCM decisions." A push of org structure fits that direction; a collab-initiated
  pull would not.
- Exporting the tree to a platform where everyone can see it is a **deliberate declassification** of an
  INTERNAL-tier field. That is defensible — org charts are normally internal-public — but it should be a
  recorded decision (an ADR), not a side effect of an integration.
- Sync shape needs designing: what is pushed (name, title, department, manager — almost certainly not
  grade, location or employment status), how it stays current as people move, and what happens to a
  terminated or suspended person's node.
| 4 | **Workforce planning — budget half** | Unplanned | Positions/establishment shipped (C1 ①). Budget/establishment cost modelling against those posts did not, and isn't on the backlog. |

### A2. Workflows

| # | Capability | Status | Note |
|---|---|---|---|
| 5 | **Open-enrollment windows** | Unplanned | Benefits elections are permanently open; there is no campaign/window concept. The only workflow in the reference survey with no path at all. |
| 6 | **Generic compliance-deadline framework** | Unplanned | Instances keep getting hand-built (EE report stage gates, now contract end-dates). No shared framework, and none planned. |
| 7 | **Multi-channel escalation (SMS / push)** | Unplanned | Notifications are in-app + best-effort email. No SMS, no push, no per-employee channel preference. |

### A3. Integrations

| # | Capability | Status | Note |
|---|---|---|---|
| 8 | **Benefits carriers (EDI 834)** | Unplanned | Catalogue is modelled internally; no carrier feed. |
| 9 | **Background-check vendors** | Unplanned | SA vetting is often manual/legal rather than API-shaped — low leverage. |
| 10 | **Job boards / sourcing** | Partly parked | Not on C1–C7. Overlaps the parked internal-first posting idea (intranet first, then PNet/Career24/LinkedIn after a timeout) — see `project_hr_system_recruitment_posting_idea`. |
| 11 | **Learning content marketplaces** | Unplanned | The WSP/ATR-oriented model already serves the statutory need. |
| 12 | **Accounting / ERP (GL posting)** | Unplanned | SAP referenced conceptually; no live connection. |
| 13 | **Slack / Teams** | Has an analog | Outbound push to the sibling collab platform. The vendors themselves aren't planned. |
| 14 | **Time-clock hardware** | Has an analog | Browser liveness + geofence, scoped to payroll integrity rather than minute-tracking. |

### A4. Deliberately ceded — recorded so they aren't re-raised as gaps

- **Payroll run + statutory filing** → stays in SAP (`ROADMAP-2026-08.md` §4).
- **Time & attendance clocking** → stays in SAP; read-only mirror only, via C3.
- **External e-signature vendor** → rejected in favour of the in-house ECT Act implementation.
- **Policy chatbot / RAG / LLM** → ADR-008, waits on a vendor + abuse-prevention sign-off.

### A5. Needs a decision, not just a plan

| # | Capability | Why it's different |
|---|---|---|
| 15 | **Leave / absence management** | Currently ceded to SAP ("mirror only", C3) — but **nothing exists today**, not even the mirror. Meanwhile the Policy Library ships a *Leave Policy* document describing BCEA entitlements with no system behind it. Leave is the single most frequent HR interaction there is, and its absence is the most conspicuous hole in any demo. Either the mirror gets built (C3) or the decision to cede it gets revisited. Leaving it in limbo is the one outcome that serves nobody. |

---

## Part B — The demoable lifecycle

### What already works

Thirteen apps, all genuinely functional: employee directory + versioned history, org structure reference data,
positions/establishment with an approval chain, recruitment pipeline through to hire, performance contracting
with e-signatures and evidence, learning records, pay bands + comp proposals + benefits elections, policy library
with acknowledgment tracking, EEA2/EEA4 statutory reporting, audit log viewer, notifications, workforce-integrity
liveness checks, and contract renewals.

### Why it doesn't demo as a system

There is no **journey**. A demo today is a tour of thirteen admin screens, not a walk through how HR actually
works. Take one employee from arrival to departure and the breaks are obvious:

| Lifecycle step | State | Blocker |
|---|---|---|
| Recruit → offer → hire | ✅ Works | — |
| **Onboard** (tasks, IT, first week) | ❌ Missing | C1 ③ — planned, not started |
| Profile, org placement | ✅ Works | — |
| **See the org visually** | ❌ Missing | A1 #3 — unplanned |
| **Personal documents** (ID, contract, quals) | ❌ Missing | C2 — planned, not started |
| **Request leave** | ❌ Missing | A5 #15 — needs a decision |
| Performance cycle | ✅ Works (deep) | — |
| Contract renewal | ✅ Works | C1 ② — shipping now |
| **Offboard** (exit cascade) | ❌ Missing | C1 ③ — planned, not started |

Five breaks. Three are already on the backlog (C1 ③ ×2, C2). One is unplanned but cheap (org chart). One
needs a decision (leave).

### The reframing

The MVP goal stops being "close gaps against a reference platform" and becomes:

> **One employee, start to finish, demonstrable in a single sitting.**

That reorders the backlog around a journey instead of a dependency graph. It also front-loads the parts an HR
stakeholder will react to — which is what generates the feedback that makes the next round of decisions real,
per the original brief's own reasoning (build a standard process, demo it, let HR tell us where it's wrong).

### Proposed sequence

1. **C1 ③ — onboarding + offboarding checklists.** Closes two of the five breaks at once, and offboarding
   carries the integrity payload the Gap Survey flagged: a terminated employee should automatically drop out of
   liveness checks and role assignments.
2. **C2 — employee documents.** Closes the third break; the consent/tiering plumbing already exists, so this is
   mostly a new model plus the policies module's existing download pattern.
3. **Org chart view.** Small, unplanned, disproportionate demo value — the data is already there.
4. **Leave — decide, then build or mirror.** Highest demo value of anything on this list; blocked on a decision
   rather than on effort.

Everything else on the C-series (C3 SSO/SAP, C4 delegation, C5 labour relations, C6 talent depth, C7 UX/NFR)
stays where it is, sequenced after a coherent lifecycle exists to hang it on.
