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
