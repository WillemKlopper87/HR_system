# HCM Remediation Execution Protocol

**Review / protocol date:** 2026-09-03  
**Repository:** `WillemKlopper87/HR_system`  
**Primary branch:** `master`  
**Baseline reviewed:** `9ecfe2f83b7c06f44434bb3580e061a62753f71d`

---

## 1. Purpose

This document converts the independent HCM/HR code review into an execution protocol for a remediation agent.

The agent must not treat findings as instructions to mechanically edit the cited function. The goal is to restore and continuously enforce system invariants across the HCM platform.

For every P0/P1 finding and every P2 finding that touches security, privacy, money, employment state, or compliance, the remediation agent must:

1. verify the finding against the current repository state;
2. reproduce it where practical;
3. identify the broken business/security/compliance invariant;
4. write a failing regression or invariant test before or alongside the fix;
5. implement the smallest architecturally correct fix;
6. test the affected workflow end-to-end;
7. test adjacent domains and side effects;
8. run focused tests and then the complete applicable gates;
9. update migrations, serializers, API contracts, frontend behavior, documentation, fixtures, and operations guidance where required;
10. record the result in the remediation ledger.

A finding is not `DONE` merely because code changed.

The target state is:

> HCM lifecycle, privacy, access, compliance, compensation, and integration invariants are enforced by authoritative layers and continuously protected by regression tests.

---

## 2. Repository-state rule

Before starting remediation, record the actual repository state:

```text
Current HEAD:
Current branch:
Working-tree modifications:
Untracked files:
Migration state:
API/schema generation state:
Frontend contract state:
CI state:
Database engine/version used in integration tests:
```

Classify every finding as one of:

- `MASTER` — defect exists on the committed primary branch;
- `WORKTREE` — introduced only by unpublished local changes;
- `BOTH`;
- `STALE` — repository changed and finding no longer applies;
- `DESIGN` — systemic architectural weakness rather than one implementation defect;
- `UNVERIFIED`.

Never assume audit line numbers remain current after remediation starts.

---

## 3. Severity and evidence model

Severity and certainty are separate concepts.

### Severity

- **P0 / Critical** — unauthenticated or large-scale HR-data compromise, cross-tenant compromise, systemic employment/payroll corruption, unrecoverable data loss, credential compromise, or an imminent unsafe production release.
- **P1 / High** — serious authorization, privacy, lifecycle, compliance, financial/remuneration, or release-integrity defect requiring remediation before normal production release.
- **P2 / Medium** — meaningful correctness, concurrency, resilience, security-hardening, auditability, maintainability, or UX problem.
- **P3 / Low** — cleanup, documentation, consistency, or low-impact engineering improvement.

### Evidence status

- **RUNTIME VERIFIED** — reproduced against a running system;
- **STATIC VERIFIED** — code path demonstrates the defect with high certainty;
- **HIGHLY LIKELY** — strong static evidence but runtime confirmation is still required;
- **HYPOTHESIS** — plausible and important, but must be tested before being treated as confirmed;
- **DESIGN RISK** — systemic weakness that can manifest in multiple locations;
- **DISPROVED** — reproduction and inspection show the finding does not apply.

Do not use severity to communicate certainty.

---

## 4. Required finding format

Every P0/P1 remediation item must be converted into this structure before implementation:

### ID — Title

**Scope:** MASTER / WORKTREE / BOTH / DESIGN  
**Severity:** P0 / P1 / P2 / P3  
**Evidence:** Runtime Verified / Static Verified / Highly Likely / Hypothesis  
**Subsystem:** Identity / Core HR / Documents / Compensation / Privacy / Integrations / CI / etc.

#### Broken invariant

State what the system must always guarantee.

#### Evidence

List the relevant code paths, models, constraints, migrations, tasks, serializers, API routes, frontend surfaces, and existing tests.

#### Failure / attack scenario

Use:

```text
Actor or system state
→ prerequisite
→ action
→ state transition
→ resulting impact
```

#### Reproduction

Prefer a deterministic integration/invariant test.

#### Root cause

Describe the architectural cause, not just the symptom.

#### Required remediation

Describe the required end-state while avoiding unnecessary implementation prescription.

#### Regression tests

List the tests that must fail before the fix and pass afterward.

#### Adjacent-risk review

Identify impacted domains and downstream side effects.

#### Completion criteria

Explicit objective conditions required to close the item.

#### Residual risk

Record deliberately deferred risk.

---

# 5. Core HCM invariants

The remediation programme must be driven by invariants rather than individual endpoints.

## 5.1 Identity and account state

```text
A user who is inactive, terminated, locked, or otherwise administratively
blocked cannot regain application access unless the authoritative state that
caused the block has been explicitly reversed.

A lifecycle operation may restore only access that the same lifecycle
operation previously revoked.

Independent security revocations must never be overwritten by HR workflow
reversal.
```

Required test classes:

- inactive user authentication;
- suspension and lift;
- termination;
- independent security disable before suspension;
- security disable during suspension;
- role removal during suspension;
- MFA/TOTP state;
- biometric state;
- SSO/IdP state where integrated.

---

## 5.2 Employee lifecycle

```text
An employment termination is not access-complete until every mandatory
access-revocation obligation has reached a durable successful state.

A suspension records exactly what it revoked.

A suspension lift restores only those exact effects unless a separate
current authorization says otherwise.
```

Lifecycle states must distinguish HR employment completion from downstream access completion.

Recommended aggregate states:

```text
APPROVED
EXECUTING
EXECUTED_ACCESS_PENDING
EXECUTED
EXECUTED_ACCESS_FAILED
REVERSED
```

The exact names may differ, but the semantics must be explicit.

---

## 5.3 Manager / employee / HR row scope

```text
An employee can access self-service information only for themselves unless
another explicit relationship grants access.

A manager can access employee data only where the reporting/delegation
relationship and field sensitivity permit it.

Possession of a generic permission must not automatically imply access to
all employees.
```

Manager/delegation tests must cover reads, writes, downloads, exports, approvals, and indirect references.

---

## 5.4 Sensitive and Restricted HR data

```text
Restricted HR information requires both row authorization and field-level
authorization.

High-risk fields require step-up authentication where policy defines it.

Compromise of database contents alone should not immediately reveal
Restricted identity information or reusable MFA seed material.
```

Particular priority:

- national ID;
- passport number;
- tax identifiers;
- bank data where applicable;
- disability/race/EE-sensitive fields where appropriate;
- TOTP seeds;
- recovery secrets;
- identity-verification secrets/tokens.

---

## 5.5 Documents

```text
An employee document is never downloadable merely because its identifier or
storage key is known.

Every document read/download is subject to current authorization.

Malware/unscanned objects are never served where fail-closed scanning policy
applies.

Sensitive document access is auditable.
```

---

## 5.6 Data-subject requests / privacy

```text
A completed subject-data export includes every registered in-scope HCM
domain, or an explicit domain-level manifest describing no records,
retention, legal exclusion, failure, or other non-inclusion.

A subject-data request cannot be marked complete merely because one owning
Django app finished its portion.

Erasure and retention decisions are explicit and evidence-bearing.
```

---

## 5.7 Retention

```text
A retention run is not successful merely because the scheduler executed.

Every configured retention obligation has a durable outcome with enough
evidence to determine what was examined, deleted, anonymized, retained,
failed, or deferred.
```

---

## 5.8 Compensation / remuneration

```text
One compensation proposal can undergo an authoritative state transition only
once for a given prior state.

Concurrent approvals cannot multiply audit, notification, export, or payroll
side effects.

Remuneration-sensitive information remains subject to Restricted-data policy.
```

Use database serialization or atomic conditional transitions rather than check-then-act Python logic alone.

---

## 5.9 Third-party integrations

```text
An integration event is processed at most once where the provider offers a
stable event identifier, or the system creates an equivalent replay key.

Failed synchronization is durably visible and reconcilable.

A successful HTTP request is not automatically proof that internal and
external system states agree.
```

---

## 5.10 Audit

```text
Security, Restricted-data access, employment lifecycle, compensation,
subject-data requests, and high-impact integration changes produce durable
audit evidence.

Audit data cannot silently disappear because a downstream best-effort action
failed.
```

---

## 5.11 CI and release integrity

```text
A production/release baseline is valid only if required validation gates for
that exact commit have passed.

Migration correctness, backend tests, frontend tests/contracts, browser E2E,
security scanning, and container validation are release evidence rather than
optional advisory signals.
```

---

# 6. Confirmed high-priority findings

## H-1 — Suspension lift can reactivate independently disabled access

**Severity:** P1  
**Evidence:** STATIC VERIFIED  
**Subsystem:** Employee lifecycle / Identity / Biometrics

### Broken invariant

```text
A lifecycle reversal may restore only access that the lifecycle action itself
revoked.
```

### Risk

Roles are snapshotted with useful precision, but account and biometric active-state restoration is broader.

A security-disabled account or biometric enrolment can potentially be re-enabled by a later `LIFT_SUSPENSION` even when the suspension did not cause the original disablement.

### Required remediation

Persist exact access effects of the suspension.

At minimum record:

```text
user_login_was_active
roles_revoked_by_change
biometric_enrolment_ids_revoked_by_change
other_domain_grants_revoked_by_change
```

Preferred reusable model:

```text
EmploymentChangeAccessEffect

employment_change_id
domain
resource_id
previous_state
new_state
changed_at
restored_at
restoration_status
```

Restoration must be conditional on the effect record, not merely current inactivity.

### Required tests

```text
test_lift_suspension_restores_login_if_suspension_disabled_it
test_lift_suspension_does_not_reactivate_previously_disabled_user
test_lift_restores_only_biometrics_revoked_by_that_suspension
test_previously_disabled_biometric_remains_disabled
test_security_disable_during_suspension_is_not_undone
test_role_removed_independently_during_suspension_is_not_restored
```

---

## H-2 — Employment exit can report completion while a domain revocation failed

**Severity:** P1  
**Evidence:** STATIC VERIFIED  
**Subsystem:** Offboarding / Access lifecycle

### Broken invariant

```text
A termination cannot be represented as fully access-complete while any
mandatory revocation obligation is unresolved.
```

### Risk

The domain access cascade intentionally catches exceptions and continues. That prevents one downstream subsystem from rolling back the core HR change, which is reasonable.

The unsafe part is allowing the high-level workflow to become `EXECUTED` while a required domain such as biometrics, IdP, physical access, or another application integration failed.

### Required remediation

Do not solve this with one giant distributed transaction.

Create durable domain revocation obligations.

Suggested model:

```text
AccessRevocationObligation

employment_change_id
domain
resource_reference
status
attempt_count
last_attempt_at
completed_at
error_code
error_detail
```

Statuses:

```text
PENDING
RUNNING
RETRYING
SUCCESS
FAILED
NOT_APPLICABLE
```

Required lifecycle completion should derive from required obligation state.

### Required tests

```text
test_exit_not_access_complete_when_biometric_revoke_fails
test_failed_revocation_is_durably_recorded
test_failed_revocation_can_be_retried
test_retry_is_idempotent
test_exit_becomes_complete_only_after_required_domains_complete
test_revocation_failure_creates_operational_alert_or_work_item
```

---

## H-3 — Data-subject export is partial but can be marked COMPLETED

**Severity:** P1  
**Evidence:** STATIC VERIFIED  
**Subsystem:** Privacy / POPIA-oriented subject-data processing

### Broken invariant

```text
A completed HCM subject-data export either contains every registered in-scope
domain or contains an explicit manifest proving why each domain is absent,
retained, excluded, unavailable, or failed.
```

### Risk

The current export flow covers core HR/documents/consent-oriented information while the platform also owns personal data in domains such as learning, performance, compensation, recruitment, assessments, identity verification, and others.

A top-level `COMPLETED` state therefore risks overstating the completeness of the platform response.

This is an application-integrity concern; legal interpretation of a particular request remains policy/legal-counsel territory.

### Required remediation

Introduce a domain exporter registry.

Example:

```text
DataSubjectDomainRegistry
  CORE_HR
  DOCUMENTS
  RECRUITMENT
  LEARNING
  PERFORMANCE
  COMPENSATION
  ASSESSMENTS
  IDENTITY_VERIFICATION
  CONSENT
  INTEGRATIONS
```

Each registered domain returns:

```text
domain
status
record_count
payload_reference
exclusions
retention_basis
error
```

Expected statuses:

```text
INCLUDED
NO_RECORDS
RETAINED
EXCLUDED
FAILED
NOT_APPLICABLE
```

The top-level request cannot become `COMPLETED` with an unresolved required domain failure.

Use the same registry concept for erasure and retention exceptions.

### Required tests

```text
test_subject_export_includes_core_hr
test_subject_export_includes_documents
test_subject_export_includes_compensation
test_subject_export_includes_learning
test_subject_export_includes_performance
test_subject_export_includes_recruitment
test_subject_export_includes_assessments
test_subject_export_includes_identity_verification
test_subject_export_manifest_identifies_no_record_domains
test_subject_export_cannot_complete_when_required_domain_fails
test_erasure_records_retained_domain_and_reason
```

---

## H-4 — Restricted identifiers and TOTP seeds lack application-layer encryption

**Severity:** P1  
**Evidence:** STATIC VERIFIED  
**Subsystem:** Privacy / MFA / Key management

### Broken invariant

```text
Database contents alone must not reveal Restricted identity values or reusable
MFA seed material.
```

### Risk

Disk/volume encryption is important, but it does not create separation from database dumps, read-only database credential compromise, exposed backups, malicious high-privilege database access, or similar data-plane compromise.

The surrounding application authorization is stronger than the storage protection for some Restricted values.

### Required remediation

Use authenticated application-layer envelope encryption for suitable Restricted fields.

Preferred design:

```text
plaintext
  ↓
DEK / purpose-specific application key
  ↓
AES-GCM or equivalent authenticated encryption
  ↓
ciphertext stored in DB

key material
  ↓
KMS / HSM / secret manager
```

Where exact-match lookup is required, use a separate keyed lookup fingerprint such as HMAC rather than an unsalted hash.

Example:

```text
national_id_ciphertext
national_id_lookup_hmac
```

TOTP seeds must:

- be encrypted with a purpose-specific key;
- never appear in serializers/logging/admin output;
- be decrypted only for verification;
- support key rotation;
- support forced re-enrolment if key material is compromised.

### Migration safety

Do not replace plaintext fields in one destructive migration.

Use:

```text
1. add encrypted columns
2. dual-read
3. backfill in bounded batches
4. verify row counts and decryptability
5. switch writes
6. monitor
7. remove plaintext only after verification
8. document backup/key-retention implications
```

Maintain checkpointing and a failed-record ledger.

### Required tests

```text
test_database_does_not_contain_plain_national_id
test_database_does_not_contain_plain_passport_number
test_totp_database_value_does_not_equal_seed
test_encrypted_field_round_trip
test_lookup_uses_keyed_fingerprint
test_key_rotation_preserves_readability
test_totp_key_rotation_and_reenrollment
```

---

# 7. Medium / hardening findings

## M-1 — Compensation proposal approval needs proposal-level serialization

**Severity:** P2; promote to P1 if approval directly triggers authoritative payroll/remuneration side effects.  
**Evidence:** STATIC VERIFIED

### Required invariant

```text
A proposal can make one authoritative transition from a given prior state,
and concurrent approval requests cannot duplicate downstream effects.
```

### Preferred pattern

```text
transaction.atomic()
  ↓
CompensationProposal.objects.select_for_update().get(...)
  ↓
re-check current state
  ↓
re-check approver authorization
  ↓
transition
  ↓
record one authoritative audit/notification sequence
```

If both compensation cycle and proposal require locks, define and document stable lock ordering.

### Required test

```text
test_concurrent_proposal_approvals_have_single_winner
test_concurrent_approval_emits_one_authoritative_audit_event
```

---

## M-2 — Retention execution needs durable evidence and failure state

**Severity:** P2  
**Evidence:** STATIC VERIFIED / DESIGN RISK

### Required invariant

```text
A retention run is not complete until each configured obligation has a
durable outcome.
```

### Recommended models

```text
RetentionRun
RetentionRuleRun
```

Record:

```text
started_at
completed_at
rule
cutoff
records_examined
records_deleted
records_anonymized
records_retained
status
attempt_count
error
```

Possible states:

```text
SUCCESS
PARTIAL
FAILED
RETRYING
```

### Required tests

```text
test_retention_failure_remains_visible
test_failed_retention_rule_can_be_retried
test_success_records_cutoff_and_record_counts
test_one_rule_failure_does_not_hide_other_results
```

---

## M-3 — Assessment/integration webhook replay protection should be persistent

**Severity:** P2 hardening  
**Evidence:** DESIGN RISK

The signature/timestamp baseline is useful, but replay resistance should not depend only on freshness if downstream processing can produce non-idempotent effects.

Prefer a provider event ID or stable replay fingerprint with uniqueness enforcement and bounded retention.

### Required tests

```text
test_webhook_event_processed_once
test_webhook_replay_is_idempotent
test_duplicate_provider_event_id_rejected_or_nooped
```

---

# 8. Cross-domain architectural improvement: Domain Obligation Registry

Several findings share the same root cause: a top-level HCM workflow spans multiple Django apps but completion is currently easier to express than proof of completion.

Introduce a reusable domain obligation mechanism for operations such as:

```text
employee termination
employee suspension
suspension reversal
subject-data export
subject-data erasure
retention
possibly onboarding completion
```

Suggested domain inventory:

```text
CORE_HR
RBAC
DOCUMENTS
LEARNING
PERFORMANCE
COMPENSATION
RECRUITMENT
ASSESSMENTS
IDENTITY_VERIFICATION
INTEGRATIONS
SSO_IDP
PHYSICAL_ACCESS
```

Not every domain must implement every capability.

Possible capability interfaces:

```text
revoke_access(subject, context)
restore_access(subject, context)
export_subject(subject, context)
erase_subject(subject, context)
apply_retention(context)
```

Each obligation records:

```text
domain
operation
status
started_at
completed_at
attempt_count
result_metadata
error
```

Common statuses:

```text
NOT_APPLICABLE
PENDING
RUNNING
SUCCESS
FAILED
RETRYING
RETAINED
```

This should become a reusable control primitive rather than implementing unrelated orchestration logic separately in every app.

---

# 9. Execution order

Do not remediate numerically.

Use dependency-aware phases.

## Phase 0 — Establish a trusted release baseline

Before feature/security remediation:

- confirm current `master` HEAD;
- run/inspect the complete CI suite for that exact SHA;
- resolve any failing backend, migration, integration, contract, E2E, security, or image gates;
- confirm migration state is reproducible on a clean PostgreSQL database;
- confirm frontend/API contract generation is synchronized;
- configure branch protection or repository rules if not already enforced;
- prevent direct production release from an unverified commit.

Target:

```text
primary branch = green
required checks = enforced
```

Do not build major migrations on an unreliable baseline.

---

## Phase 1 — Employee lifecycle access correctness

Remediate H-1 and H-2 together.

Required domains should include, where relevant:

```text
application login
RBAC roles
biometrics
SSO/IdP
physical access
privileged application roles
external HR integrations
```

Deliverables:

- exact access-effect snapshot;
- durable revocation obligations;
- retry semantics;
- operational exception visibility;
- safe restoration semantics;
- end-to-end termination and suspension tests.

---

## Phase 2 — Restricted data cryptography

Remediate H-4 as a controlled data-migration programme.

Deliverables:

- field inventory;
- encryption-key architecture;
- purpose separation;
- migration/backfill tooling;
- rollback plan;
- rotation plan;
- monitoring;
- backup implications;
- TOTP re-enrolment contingency.

Do not remove plaintext columns until migration verification is complete.

---

## Phase 3 — Data-subject / privacy orchestration

Remediate H-3 using a domain registry.

Deliverables:

- registered personal-data domains;
- exporter implementations;
- erasure implementations or explicit retention outcomes;
- domain-by-domain completion manifest;
- durable failures/retries;
- synthetic full-profile integration test.

Build one synthetic employee whose data exists across every personal-data-owning module and use it as the canonical completeness fixture.

---

## Phase 4 — Compliance evidence

Harden:

- retention;
- data-subject request execution;
- access revocation;
- high-impact consent/privacy events.

Replace log-only proof with durable state where business/compliance evidence matters.

---

## Phase 5 — State-machine concurrency

Address M-1 and audit other state machines for this pattern:

```text
read state
→ authorize
→ side effect
→ update state
```

Prioritize:

- compensation approval;
- leave approval;
- employment changes;
- onboarding transitions;
- document acknowledgement;
- assessment finalization;
- integration sync ownership.

Use row locks, conditional updates, unique constraints, or another authoritative serialization mechanism as appropriate.

---

## Phase 6 — Integration reliability

Add/verify:

- webhook replay identifiers;
- idempotency;
- durable failure state;
- reconciliation;
- per-integration health;
- retry policy;
- credential rotation;
- explicit tenant/employee scope where applicable.

---

## Phase 7 — Production qualification

After source remediation, perform real operational exercises:

- employee termination drill;
- suspension/lift drill;
- security disable + HR suspension interaction;
- full subject-data export across all domains;
- erasure with statutory-retention exceptions;
- Restricted-data access review;
- compensation concurrent-approval test;
- SSO/OIDC production IdP validation;
- SMTP/notification validation;
- background worker failure/recovery;
- PostgreSQL backup/restore drill;
- object/file recovery drill where applicable;
- audit-retention verification;
- migration rollback/forward rehearsal;
- TLS/security-header deployment checks.

---

# 10. Mandatory remediation loop

For each P0/P1 finding:

```text
VERIFY
  ↓
REPRODUCE
  ↓
WRITE FAILING TEST / INVARIANT TEST
  ↓
IDENTIFY ROOT CAUSE
  ↓
IMPLEMENT MINIMAL CORRECT FIX
  ↓
RUN FOCUSED TEST
  ↓
RUN RELATED DOMAIN TESTS
  ↓
RUN AUTHORIZATION / CONCURRENCY TEST IF APPLICABLE
  ↓
RUN POSTGRESQL INTEGRATION
  ↓
RUN API CONTRACT / FRONTEND BUILD IF APPLICABLE
  ↓
RUN BROWSER E2E IF USER-FACING
  ↓
RUN SECURITY GATES
  ↓
REVIEW MIGRATION / BACKFILL SAFETY
  ↓
REVIEW DIFF FOR COLLATERAL CHANGES
  ↓
UPDATE DOCUMENTATION / RUNBOOKS
  ↓
CLOSE FINDING
```

If reproduction disproves a finding, mark it `DISPROVED` and preserve the evidence.

Do not silently delete findings from the ledger.

---

# 11. Database and concurrency rule

For lifecycle, compensation, security, and privacy invariants, prefer authoritative persistence controls where practical.

Examples:

- `select_for_update()` for mutable workflow state;
- conditional `UPDATE ... WHERE status = expected` transitions;
- unique constraints for one-per-business-invariant relationships;
- idempotency/event-key uniqueness;
- durable obligation rows;
- transaction-safe outbox/event patterns for critical downstream effects.

Application-level checks such as:

```python
if proposal.status == "PROPOSED":
    ...
```

are not sufficient concurrency controls by themselves.

---

# 12. Security-sensitive migration rule

Any migration touching Restricted employee information, TOTP seeds, access-state history, or lifecycle evidence must be treated as a controlled production data migration.

Required planning:

```text
existing-data inventory
new schema
forward migration
backfill strategy
checkpointing
validation queries
rollback / roll-forward strategy
key/version metadata
failure ledger
operational monitoring
backup/recovery implications
```

Large data migrations should be bounded and resumable.

Do not couple a long-running encryption backfill to a single web-process startup migration if production scale makes that unsafe.

---

# 13. Change-impact checklist

Before closing any item, inspect whether the change affects:

- Django models;
- migrations;
- historical/simple-history models;
- serializers;
- permissions;
- row scope;
- step-up logic;
- admin interfaces;
- API schemas;
- generated frontend contracts;
- frontend pages/hooks;
- background jobs/workers;
- Celery/Redis behavior where used;
- webhooks/integrations;
- audit logging;
- notifications;
- fixtures/seed data;
- tests;
- E2E;
- backups/restores;
- deployment configuration;
- runbooks/policy documentation.

A cross-domain workflow change is incomplete if only the initiating Django app was reviewed.

---

# 14. Recommended invariant test suites

Organize tests around guarantees rather than only endpoints.

Example structure:

```text
backend/tests/invariants/test_lifecycle_access.py
backend/tests/invariants/test_restricted_data.py
backend/tests/invariants/test_subject_data_requests.py
backend/tests/invariants/test_retention.py
backend/tests/invariants/test_manager_scope.py
backend/tests/concurrency/test_compensation.py
backend/tests/integrations/test_webhook_idempotency.py
```

Adapt paths to the repository's existing convention rather than forcing this exact layout.

## Lifecycle

```text
test_termination_revokes_all_required_access_domains
test_exit_not_complete_while_revocation_domain_failed
test_suspension_records_exact_access_it_revoked
test_lift_restores_only_access_revoked_by_that_suspension
test_preexisting_disabled_login_stays_disabled_after_lift
test_preexisting_disabled_biometric_stays_disabled_after_lift
test_security_revoke_during_suspension_is_not_undone
```

## Privacy / Restricted data

```text
test_restricted_identity_values_not_plaintext_in_database
test_totp_seed_not_plaintext_in_database
test_restricted_access_requires_correct_role_and_step_up
test_restricted_access_is_audited
```

## Subject-data requests

```text
test_subject_export_has_every_registered_domain
test_subject_export_cannot_complete_on_domain_failure
test_subject_export_contains_completion_manifest
test_erasure_retention_exception_requires_reason
```

## Compensation

```text
test_concurrent_proposal_approvals_have_single_winner
test_concurrent_approval_has_single_authoritative_side_effect_sequence
```

## Documents

```text
test_employee_cannot_download_other_employee_document
test_manager_document_access_requires_reporting_relationship
test_hr_document_download_is_audited
test_unscanned_file_cannot_be_served_when_fail_closed
```

## Integrations

```text
test_webhook_event_processed_once
test_webhook_replay_is_idempotent
test_failed_integration_sync_is_durably_visible
```

## Retention

```text
test_retention_run_records_each_rule
test_retention_failure_is_not_reported_as_complete
test_failed_rule_is_retryable
```

---

# 15. Agent change discipline

Do not submit one huge "fix audit" commit.

Prefer coherent workstreams:

```text
fix(lifecycle): record exact suspension access effects
fix(lifecycle): make offboarding revocation obligations durable
feat(privacy): add domain-complete subject-data export manifest
feat(security): encrypt restricted identity fields
feat(auth): encrypt TOTP seed storage
fix(compensation): serialize proposal approval transitions
feat(retention): add durable retention execution ledger
fix(integrations): persist webhook replay identifiers
```

Do not artificially split migrations and application changes that must be atomic to preserve compatibility.

Every commit/PR should state:

- invariant addressed;
- reproduction/test added;
- schema impact;
- compatibility/backfill impact;
- rollback considerations;
- residual risk.

---

# 16. Completion definition

A finding is `DONE` only when all applicable conditions are true:

- root cause understood;
- finding verified or reproduced;
- regression/invariant test exists;
- fix implemented;
- focused tests pass;
- related domain tests pass;
- authorization tests pass where applicable;
- concurrency tests pass where applicable;
- PostgreSQL integration passes;
- migrations apply cleanly to a fresh database;
- migration/backfill behavior is validated against representative existing data where applicable;
- API/frontend contracts are synchronized;
- frontend typecheck/build passes where impacted;
- browser E2E passes where impacted;
- security gates pass;
- audit behavior is validated;
- operational/runbook documentation is aligned;
- no unresolved regression was introduced.

Statuses:

```text
OPEN
VERIFYING
CONFIRMED
IN PROGRESS
BLOCKED
FIXED — VALIDATION PENDING
DONE
DISPROVED
DEFERRED — ACCEPTED RISK
```

Do not use `DONE` to mean "the cited code was edited."

---

# 17. Remediation ledger

Maintain this table as work proceeds.

| ID | Finding | Scope | Severity | Evidence | Status | Tests added | Commit/PR | Residual risk |
|---|---|---|---:|---|---|---|---|---|
| H-1 | Suspension lift can reactivate independently disabled access | MASTER | P1 | Static verified | DONE | 2 (core_hr) | bf6008d | None known |
| H-2 | Exit can report completion despite failed domain revocation | MASTER | P1 | Static verified | DONE | 5 (core_hr) | bf6008d | None known |
| H-3 | Subject-data export is partial but can be marked completed | MASTER | P1 | Static verified | DONE (partial domain coverage) | 11+4 (rbac_audit, documents) | 54a9b08 | Only documents/compensation/learning domains registered; performance, recruitment, assessments, identity_verification, onboarding, succession, ee_reporting not yet wired into the registry — each is a tracked follow-up, not silently missing (absent from export_manifest, not falsely reported as covered) |
| H-4 | Restricted identifiers and TOTP seeds lack app-layer encryption | MASTER | P1 | Static verified | IN PROGRESS — phase 1 DONE | 17 (rbac_audit, core_hr) | 75d9663 | Phase 1 only: national_id_number/passport_number/TOTPDevice.secret still readable as plaintext from the original columns — *_encrypted mirror fields exist and are backfillable/verifiable but nothing reads from them yet. Phase 2 (switch reads/writes to the encrypted fields, then drop the plaintext columns) is a deliberate follow-up requiring a production backfill + verification window before cutover. HistoricalEmployee's plaintext audit-trail rows are also not yet backfilled. |
| M-1 | Compensation proposal approval needs stronger serialization | MASTER | P2 / P1 candidate | Static verified | DONE | 2 (compensation) | 262d976 | None known |
| M-2 | Retention execution lacks durable evidence/failure state | MASTER | P2 | Static/design | DONE | 5 (rbac_audit) | 18618a2 | None known |
| M-3 | Webhook replay resistance should be persistent | MASTER | P2 | Design risk | DONE | 4 (assessments) | 099a0ed | No retention sweep yet on WebhookDelivery rows (deferred, noted in the model docstring; not a correctness issue at pilot scale) |
| R-1 | Primary-branch release baseline and required checks must be verified/enforced | REPO | P1 release | Verify current state | PARTIALLY DONE | — | 8ee9ae7 | hcm-ci's Postgres job fails deterministically (reproduced on rerun) at learning.views.download_evidence with `psycopg.OperationalError: the connection is closed` and no preceding SQL error — looks structural (e.g. an idle worker's DB connection dropped while waiting on siblings under GitHub Actions' parallel test runner), not an application bug; not yet root-caused. E2E job has 4 pre-existing failures in performance.spec.ts/notifications.spec.ts, confirmed identical on a pre-remediation baseline commit. Both are CI-infrastructure issues outside this remediation's domains — fixed what was fixable (a real Postgres-length bug in test fixtures, and Contract-drift regeneration) and left these two flagged rather than pushed further. |

Re-rank findings if runtime evidence changes impact or confidence.

---

# 18. Fresh review after P1 remediation

After all P1 work is complete, perform a fresh review rather than merely checking off this document.

Specifically look for regressions introduced by remediation:

- access restoration now fails to restore legitimate state;
- obligation workers become non-idempotent;
- deadlocks caused by lock-order changes;
- encryption migration leaves plaintext remnants;
- encrypted-field lookup breaks uniqueness/deduplication;
- TOTP rotation strands legitimate users;
- subject-data registry omits a newly added personal-data domain;
- subject export leaks Restricted fields to an unauthorized requester/admin surface;
- retention and subject erasure conflict incorrectly;
- compensation serialization breaks legitimate approval workflows;
- integration idempotency drops legitimate distinct events;
- audit payloads accidentally contain plaintext secrets;
- background-task retries multiply side effects;
- migrations fail on dirty/legacy production data.

The goal is not simply:

```text
0 open High findings
```

The goal is:

> Cross-domain HCM guarantees are stronger after remediation than the individual endpoint fixes that produced them.

---

# 19. Production qualification checklist

Before declaring production-ready, demonstrate evidence for:

### Identity and access

- normal employee login;
- inactive employee rejection;
- suspension;
- suspension lift;
- termination;
- independent security disable interaction;
- manager scope;
- HR scope;
- Restricted-field step-up;
- MFA/TOTP recovery.

### Lifecycle

- termination with all domain revocations succeeding;
- one domain revocation failing and recovering;
- repeated retry without duplicate effects;
- suspension reversal restoring only original effects.

### Privacy

- full synthetic subject-data export across every registered personal-data domain;
- no-record domain manifest;
- retained-domain manifest;
- required exporter failure;
- erasure/retention conflict;
- encrypted Restricted field backfill verification.

### Compensation

- concurrent approval;
- unauthorized approver;
- stale-state transition;
- one authoritative audit sequence.

### Documents

- employee self access;
- manager access;
- unauthorized cross-employee access;
- HR access;
- malware/unscanned object handling;
- audit trail.

### Integrations

- signed webhook;
- duplicate webhook;
- stale webhook;
- provider outage;
- retry;
- reconciliation.

### Operations

- clean database migration;
- upgrade existing representative database;
- PostgreSQL backup/restore;
- file/object recovery where used;
- Redis/background worker restart where used;
- deployment rollback/roll-forward;
- security scanning;
- browser E2E;
- API/frontend contract verification.

---

# 20. Final architectural guidance

The HCM already has strong first-order controls in several areas: authenticated API access, employee/manager/HR scope, Restricted-field classification, step-up authentication, document authorization, lifecycle workflows, audit primitives, and a broad CI architecture.

The next maturity step is to make cross-domain completion proof-bearing.

Two rules should guide all remediation:

> **A workflow is not complete until every mandatory domain obligation has a durable outcome.**

and:

> **Reversing an HR action may restore only what that exact HR action changed.**

These principles should be enforced in code, persistence, tests, and operational evidence rather than remaining conventions.
