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
