# Pilot privacy engineering review

Date: 2026-09-01

Scope: biometric identity and attendance, demographic disability information, EE forum representation, and employee
documents. This is an engineering review of repository controls and automated evidence. It is not legal advice,
independent privacy sign-off, a data-protection impact assessment, or proof of production operating practice.

## Outcome

One High-severity privacy defect was found and resolved. The identity page previously sent a derived face descriptor
before checking consent and automatically recorded consent after the server rejected that enrollment. Camera capture is
now unavailable until the employee reads the notice, affirmatively checks the consent statement, and records consent.
The consent-status endpoint is row-scoped, the biometric flow accepts only the `consent` lawful basis, and browser/API
tests cover the gate.

The same page no longer downloads the employee's complete sensitive check-in/location history. Enrollment status and
recent checks use bounded cursor pages, with explicit previous/next navigation for history.

## Findings

| ID | Severity | Area | Finding | Resolution / dependency | Status |
| --- | --- | --- | --- | --- |
| PR-001 | High | Biometrics | Enrollment attempted transmission before consent and the UI inferred consent by automatically retrying. | Added row-scoped consent status, explicit notice and affirmative checkbox; camera remains unavailable until consent is recorded; restricted lawful basis to consent. | Resolved |
| PR-002 | High | Biometrics | No implemented, independently verified non-biometric check-in and appeal workflow is present. | Requires HR policy/process ownership and an engineering workflow once the authoritative process, SLA and approvers are agreed. The UI discloses the alternative but does not claim it is operational. | Open, production-blocking for mandatory use |
| PR-003 | High | Biometrics | Consent withdrawal, descriptor disposal (including historical copies), and downstream retention behavior are not exposed as an end-to-end subject workflow. | Privacy/legal must approve retention and evidence rules; then implement withdrawal, irreversible template disposal where permitted, and regression tests. | Open, production-blocking for biometric use |
| PR-004 | Medium | Disability / accommodation | Demographic disability self-identification is consent- and tier-gated, but a separate reasonable-accommodation case domain is not implemented. | Build the planned accommodation module so minimum medical case information is not stored in demographic fields or general documents. | Open |
| PR-005 | Medium | Protected documents | ID/disability uploads are consent-aware and authenticated, but deployed storage encryption, malware scanning/quarantine and retention execution need production evidence. | Engineering/operations and the privacy reviewer must verify the production-like environment. | Open |

## Control review

### Biometrics and attendance

- Raw photos/video are processed client-side and are not a model or API response field; the server stores a derived
  128-value descriptor.
- Enrollment and every check require active biometric-purpose consent. Stored descriptors are never serialized back to
  the browser.
- Self/HR row access, auditor read-only access, HR-only review, lifecycle suspension, and human review of mismatches are
  implemented and tested.
- PR-001's explicit gate is backed by generated API contracts, nine focused enrollment API tests, and a Playwright
  journey proving the camera control is absent before affirmative consent.
- Check-in history is cursor-bounded. Formal withdrawal, retention/disposal, an operational alternative, appeal, and
  production security remain open.

### Disability information

- Race, gender, disability status and disability detail require active demographic-self-identification consent and
  Sensitive-tier access. Source provenance and sensitive-access audit paths exist.
- Aggregate reporting applies suppression rules for readers who may not see unsuppressed sensitive aggregates.
- Disability verification documents are independently consent-gated and classified Sensitive.
- Demographic self-identification must not become the accommodation case record. The planned accommodation domain and
  its narrower case team are still required.

### Union representation

- EE forum nomination basis can reveal union affiliation. The serializer removes `representation` and free-text notes
  for ordinary forum-member access; EE-authorised readers retain the fields needed for statutory consultation.
- Forum querysets limit ordinary members to their own membership and meetings attended; writes remain EE-writer only.
- An independent reviewer must still validate role assignments, conflicts, retaliation safeguards, and exports in the
  pilot environment.

### Protected documents

- Document classification is computed by type, including Restricted ID/contracts and Sensitive disability evidence.
- Raw storage URLs are write-only; downloads use authenticated, row-tier-checked endpoints.
- Upload validation records server-detected type and size, and protected types require active document-purpose consent.
- Data-subject export/erasure is a reviewed workflow with an explicit allow-list. Operational storage, scanning,
  backups, retention jobs, and restored-artifact access remain subject to deployed evidence.

## Verification evidence

- `identity_verification.test_api.EnrollmentApiTests`: 9 passed.
- Frontend generated API types refreshed successfully.
- Frontend lint and production build passed.
- Focused Playwright explicit-consent journey: 1 passed.
- Django system and migration checks, and `git diff --check`, must remain part of the tranche commit gate.

## Independent follow-up required

- Privacy/legal approval of purposes, notices, lawful bases, minimisation, retention, disposal, cross-border/vendor
  boundaries, and special-personal-information controls.
- HR-owned non-biometric check-in and appeal policy with equivalent treatment, named owners and service levels.
- Production-like verification of permissions, denial/audit evidence, storage encryption, backups/restores, malware
  handling, exports, retention and erasure.
- Recorded findings, owners, target dates and production-blocking decisions, followed by formal pilot acceptance or
  rejection.

Formal privacy review and alternative-process verification therefore remain open in `latest_todo.md`.
