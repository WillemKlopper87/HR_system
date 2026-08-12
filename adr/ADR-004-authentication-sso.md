# ADR-004: Authentication — OIDC SSO via Microsoft Entra ID

**Status:** Proposed (needs Sentech IT confirmation of app registration)

## Context
Sentech is an M365 estate. The system holds special personal information; local password databases add avoidable risk.

## Decision
OpenID Connect against Microsoft Entra ID for all staff logins. Entra group claims seed RBAC role assignment; HR admin can adjust roles in-app (audited). One local break-glass admin account, credentials stored offline.

## Consequences
- Requires an Entra app registration (IT action).
- Dev environments use a mock OIDC provider or Django local auth behind a settings flag.
- Applicants (external users, recruitment portal) are out of SSO scope — decide applicant auth in Sprint 4 planning.
