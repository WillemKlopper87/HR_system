# Pilot security engineering review

Date: 2026-09-01
Scope: authentication, payroll step-up, protected downloads, audit trails, and employee lifecycle cascades.

## Outcome

The engineering review found one High-severity issue in authenticator rotation. An authenticated user could replace
the TOTP device used for payroll step-up without re-entering their password. The issue is resolved in this tranche:
enrollment now requires the current password, and replacing a device revokes every existing step-up grant.

This document is code-review and automated-test evidence. It is not an independent security assessment, penetration
test, production-configuration review, or formal pilot approval.

## Findings

| ID | Severity | Area | Finding | Resolution | Status |
| --- | --- | --- | --- | --- | --- |
| SR-001 | High | Authentication / step-up | A valid session could rotate its TOTP authenticator without fresh primary-factor verification and could retain grants proven with the old device. | Require the account's current password at the enrollment API and UI; delete existing step-up grants before replacing the device; cover both controls with API and browser tests. | Resolved |

## Reviewed controls

- Authentication and step-up: session authentication, login/TOTP throttles, TOTP enrollment and confirmation, scoped
  payroll grants, business justification, and grant expiry/revocation paths.
- Downloads: permission and classification gates around protected employee documents and generated exports.
- Audit: sensitive reads/actions and step-up reasons are recorded through the central audit path.
- Lifecycle cascades: employee deactivation and role/access removal paths were inspected for access persistence.

No additional Critical or High code-controlled finding was identified in this focused review. That statement is
limited to the inspected repository paths and automated tests; it does not establish production security.

## Verification evidence

- 28 focused authentication, step-up, and throttling tests passed. A separate compensation payroll-step-up class added
  five passing tests.
- Frontend lint and production build passed.
- Six compensation Playwright journeys passed in the combined run. The remaining long budget journey was then updated
  for the scoped employee selector and passed independently (`1 passed`, 2026-09-01).
- The browser evidence includes current-password reauthentication, TOTP enrollment/confirmation, scoped payroll
  step-up, employee lookup, proposal creation, and budget-override enforcement.

## Required external follow-up

- Have an independent security authority review the pilot environment and record findings, owners, due dates, and
  production-blocking decisions.
- Review deployed cookie, proxy/TLS, CORS/CSRF, secret-management, logging, storage, backup, and network settings.
- Perform authenticated authorization and download testing against a production-like deployment.
- Define Entra/OIDC fresh-authentication and account-recovery semantics before enabling SSO. The current-password
  control is appropriate for the current local account flow, but must not be silently reused for federated accounts.
- Exercise deactivation, role removal, authenticator loss, session theft, stale grant, and audit-integrity scenarios in
  the pilot environment.

Formal security review and pilot acceptance therefore remain open in `latest_todo.md`.
