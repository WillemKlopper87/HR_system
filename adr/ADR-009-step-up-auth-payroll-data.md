# ADR-009: Step-up authentication for Restricted-tier payroll data (rbac_audit, unplanned addition)

**Status:** Accepted (built 2026-08-13, commit 0d6ea3a)
**Source:** originally recorded as a row in `Architecture-Design.md` §2 (kept there as the summary); this file is the
long-form record so `adr/` stays complete (H1 hardening, 2026-08-18).

## Context
Requested for `compensation.pay_band`/`comp_proposal` and `ee_reporting.remuneration_record` — the three models Data-Dictionary.md tiers "R" (Restricted) that carry actual salary figures (`recruitment.Offer`'s pay fields are also "R" but mixed with non-pay fields on one model; deliberately out of scope here, would need field-level rather than viewset-level gating — a follow-up, not done). TOTP over SMS/email OTP because no notification/SMS integration exists in this codebase yet (Architecture-Design.md's own Integration Layer table still lists email as an open gap, I2/F9) — an authenticator app needs no new vendor. Modelled on Windows Server's shutdown-reason prompt, per the request: a grant requires selecting one of a fixed set of reasons (payroll processing/audit, employee query, compliance reporting, troubleshooting, other-with-detail), and every grant is audit-logged (`AuditLogEntry.Action.STEP_UP_GRANTED`) the same way every other Restricted/Sensitive-tier access already is

## Decision
TOTP-based (RFC 6238) step-up MFA + mandatory business-justification reason, both required together in one request, time-boxed to a 15-minute grant — layered on top of the existing role check, not instead of it

## Consequences
See the corresponding entry in `Sprint-Plan-HCM-System.md` (implementation notes, design-tension callout, verification)
and the module rules in `hcm/README.md` for how the decision constrains later work.
