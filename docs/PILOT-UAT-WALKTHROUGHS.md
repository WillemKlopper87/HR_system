# HCM Pilot UAT Walkthroughs

**Status:** Ready for stakeholder execution; no stakeholder acceptance is claimed by this document.  
**Scope:** Employee, manager, HR, recruiter, compensation, employment-equity and auditor personas.  
**Evidence owner:** Pilot coordinator.  
**Execution environment:** A production-like, non-production environment using synthetic data only.

## 1. Entry criteria

Do not start a formal walkthrough until all of the following are recorded:

- Release Git SHA and deployed image tag.
- Environment URL and deployment timestamp.
- Database migration version and `/readyz` result.
- Synthetic seed/reset identifier; never use real medical, biometric, grievance or payroll information.
- Browser, browser version, viewport and assistive technology used.
- Named facilitator, stakeholder tester and evidence recorder.
- A separate test account for every persona; do not share credentials.
- Confirmation that outbound email, identity providers, payroll and other integrations are either sandboxed or disabled.

Use a fresh run ID in the form `UAT-YYYYMMDD-NN`. Store screenshots and exported evidence under that run ID in the
approved evidence repository, not in Git. Redact credentials, tokens, national identifiers, medical information and
document contents before attaching evidence.

## 2. Result and finding rules

Each step is marked `Pass`, `Fail`, `Blocked` or `Not applicable`. A pass requires observed behavior and an evidence
reference; a screenshot without the release SHA and run ID is not sufficient evidence.

Record every unexpected result in this shape:

| Field | Required value |
| --- | --- |
| Finding ID | `UAT-<run>-F<number>` |
| Persona and step | Walkthrough and step number |
| Severity | Critical, High, Medium or Low |
| Production blocking | Yes or No |
| Summary and impact | What happened and who is affected |
| Reproduction | Minimal repeatable steps |
| Evidence | Redacted screenshot, request ID or audit-event reference |
| Owner | Named accountable person, not a team alias |
| Target date | ISO date |
| Resolution evidence | Commit/release and retest reference |

Severity guidance:

- **Critical:** unauthorised Restricted data access; authentication/step-up bypass; destructive integrity loss;
  evidence-chain failure; payroll-impacting approval bypass. Always production-blocking.
- **High:** material row-scope leak, lifecycle dead end, incorrect statutory output, inaccessible critical workflow,
  or unrecoverable user action. Production-blocking unless the acceptance authority records a narrow exclusion.
- **Medium:** important workflow or usability defect with a safe workaround.
- **Low:** cosmetic, wording or low-impact consistency issue.

Formal pilot acceptance is prohibited while any Critical finding is open. Every accepted High finding requires a
documented scope exclusion, owner, target date and risk acceptance.

## 3. Cross-persona controls

Run these checks once for each persona before its workflow:

1. Sign in and verify the displayed identity and intended role.
2. Confirm navigation shows only relevant modules.
3. Attempt one copied URL outside the persona's entitlement and record the refusal/redirect.
4. Sign out, use Back, and confirm protected content is not usable from the previous session.
5. At 200% zoom and keyboard-only navigation, reach the persona's primary task with visible focus and meaningful
   accessible names.
6. Trigger one safe validation error and confirm it is understandable and associated with the relevant field.
7. Record unexpected personal fields returned by the browser network response as a privacy finding even when the UI
   does not render them.

## 4. Employee walkthrough

**Account:** Employee role with a manager, current employee version, active benefits and learning assignments.

| Step | Action | Expected result | Evidence |
| --- | --- | --- | --- |
| E-01 | Open My Profile and update an allowed contact field. | Own profile saves; restricted employment fields are not editable. | |
| E-02 | Capture demographic consent and self-identification, then reload. | Consent purpose and values persist; explanatory privacy text is visible. | |
| E-03 | Open My Benefits and elect then waive a benefit. | Only own elections change; effective state is clear. | |
| E-04 | Open My Learning, request training and download own authorised evidence. | Request is not self-approved; protected download succeeds and is audited. | |
| E-05 | Open My Performance, inspect a scorecard and nominate a 360 rater by search. | Search exposes only number/name summaries; subject and existing raters are excluded. | |
| E-06 | Complete an available employee signature/countersignature with step-up. | Password/TOTP is required; another person's credential cannot sign. | |
| E-07 | Open Probation when assigned and countersign an eligible review. | Employee can countersign only their own review; manager/HR controls are absent. | |
| E-08 | Use the non-biometric identity/check-in alternative. | The task can complete without camera/face processing and explains appeal/support. | |

Privacy checkpoint: inspect network responses for own-profile and identity pages. Record any unnecessary biometric
descriptor, third-party face template, colleague detail, medical detail or protected-document locator as a finding.

## 5. Manager walkthrough

**Account:** Line manager with at least two direct reports and one unrelated employee outside the reporting chain.

| Step | Action | Expected result | Evidence |
| --- | --- | --- | --- |
| M-01 | Open Employees and Org Chart. | Only the authorised reporting subtree is visible; unrelated search returns nothing. | |
| M-02 | Open a report's performance agreement and perform the next allowed action. | Correct stage transition succeeds; actions for unrelated staff are refused. | |
| M-03 | Create and revoke a time-bounded signing delegation. | Scope and dates are explicit; no self-delegation or privilege expansion occurs. | |
| M-04 | Create a probation review within its window. | Valid review saves; early/late and unrelated-employee attempts are refused. | |
| M-05 | Review a report's learning request. | Approval is available for a report but never for the manager's own request. | |
| M-06 | View team dashboards containing small demographic cells. | Values follow suppression rules and cannot be reconstructed from totals. | |

## 6. HR administrator walkthrough

**Account:** HR administrator with all-scope employee administration but no compensation-only assumptions.

| Step | Action | Expected result | Evidence |
| --- | --- | --- | --- |
| H-01 | Search employees and open an employee record. | Search is bounded; sensitive reads produce audit evidence. | |
| H-02 | Propose and confirm an effective-dated employment change. | History is preserved; current version changes only on valid confirmation. | |
| H-03 | Open probation, record a valid review and attempt invalid overlap/dates. | Valid lifecycle works; invalid sequences are rejected with clear errors. | |
| H-04 | Record an exit interview linked to the correct trigger. | Mismatched and multiple triggers are refused. | |
| H-05 | Manage a critical post and nominate/withdraw a successor. | Candidate search is minimal; the incumbent, duplicate and self-scope rules are enforced. | |
| H-06 | Open audit and data-quality views and trace one prior sensitive action. | Actor, action, entity and time are usable without disclosing unrelated protected content. | |
| H-07 | Attempt to countersign as the employee or submit an interview scorecard for another panelist. | Proxy action is refused. | |

## 7. Recruiter walkthrough

**Account:** Recruiter plus a separate assigned-interviewer account with no recruitment administration role.

| Step | Action | Expected result | Evidence |
| --- | --- | --- | --- |
| R-01 | Create/open an externally posted requisition and submit a portal application. | Only eligible postings appear publicly; duplicate application is handled safely. | |
| R-02 | Move the applicant through Screened to Interview. | Transition history is retained and invalid transitions are refused. | |
| R-03 | Build an interview panel using async employee search. | Multiple panelists can be added/removed; no employee directory download occurs. | |
| R-04 | Sign in as the panelist and submit a scorecard. | Only assigned sessions appear; blind-review rules apply; author is server-controlled. | |
| R-05 | Download the applicant resume as recruiter, then try as panelist. | Recruiter download succeeds and is audited; panel membership alone is refused. | |
| R-06 | Create, approve and accept an offer, then hire. | Vacancy and offer state rules hold; resulting employee link is created once. | |

## 8. Compensation walkthrough

**Account:** Compensation manager and a separate accounting-officer approver where configured.

| Step | Action | Expected result | Evidence |
| --- | --- | --- | --- |
| C-01 | Open pay bands and salary-review cycle. | Compensation data is visible only to entitled roles. | |
| C-02 | Create a proposal and inspect performance/pay-band context. | Employee search is bounded; calculated context is consistent with source records. | |
| C-03 | Exercise configured approval steps and attempt self/duplicate approval. | Server-derived next approver controls the action; invalid approvals are refused. | |
| C-04 | Close a cycle with budget pressure. | Utilisation totals reconcile and over-budget state is explicit. | |
| C-05 | Sign in as employee and open My Total Rewards. | Only own salary, band position and elected benefits appear. | |

Do not infer payroll integration from these steps. Record payroll export/import, live SAP reconciliation and production
step-up as blocked until the named provider, credentials and staging evidence exist.

## 9. Employment-equity walkthrough

**Account:** EE manager plus forum member and non-member accounts.

| Step | Action | Expected result | Evidence |
| --- | --- | --- | --- |
| EE-01 | Configure employer/sector data and create an EE plan from applicable defaults. | Version/effective dates and sector source are visible; defaults remain editable with provenance. | |
| EE-02 | Add forum members and record meeting attendance. | Selection is privacy-minimal; non-members cannot read the roster/meeting data. | |
| EE-03 | Record barriers, objectives and measures with responsible owners. | Ownership and due state are traceable; historical plan data is retained. | |
| EE-04 | Generate EEA2/EEA4 validation and inspect suppressed cells. | Completeness/arithmetic/integer checks are distinct; unauthorised viewers get suppression. | |
| EE-05 | Sign off and download authorised filing evidence. | Immutable snapshot/hash and signatory trail are visible; unauthorised download is refused. | |
| EE-06 | Inspect reminders for the selected reporting year. | Reminder reason and due date are explainable; no unverified legal deadline is silently inferred. | |

Regulatory acceptance requires a separately recorded legal review against the primary source version in force on the
test date. Passing software behavior alone is not legal sign-off.

## 10. Auditor walkthrough

**Account:** Read-only auditor with all-scope rows and no mutation grants.

| Step | Action | Expected result | Evidence |
| --- | --- | --- | --- |
| A-01 | Open employee, performance, succession and EE evidence views. | Authorised read-only data is available with applicable field-tier restrictions. | |
| A-02 | Attempt create, edit, approve, sign, withdraw and delete actions. | Mutation controls are absent or every direct API attempt is refused. | |
| A-03 | Download an authorised signed artefact and verify its displayed hash. | Download is audited; hash matches the recorded immutable artefact. | |
| A-04 | Search audit events for the walkthrough's protected reads and refusals. | Relevant actor/action/entity/timestamp records are discoverable. | |
| A-05 | Try to view the auditor's own succession nomination, if seeded. | Self-scope succession information remains hidden. | |

## 11. Security and privacy review prompts

The security reviewer records independent results for:

- Session fixation, CSRF, logout invalidation, disabled accounts and emergency access.
- Password/TOTP step-up replay, delegated signatures and proxy-action refusal.
- Direct-object access outside row scope, including protected downloads and guessed sequential IDs.
- Audit coverage for allowed and denied sensitive reads, mutations, exports and lifecycle cascades.
- File upload content validation, storage locators, retention deletion and restored artefact integrity.
- Error responses with production settings: no stack traces, secrets, tokens or provider payloads.

The privacy reviewer records independent results for:

- Data minimisation in selectors, list responses, exports and observability tooling.
- Biometric purpose/consent, non-biometric alternative, retention, appeal and vendor transfer boundaries.
- Separation of disability self-identification from reasonable-accommodation case information.
- Union/representative and witness confidentiality, including conflicts and retaliation risk.
- Small-cell suppression and resistance to reconstruction across related dashboards.
- Retention/legal-hold behavior for employee, applicant, evidence and audit records.

## 12. Exit decision

The acceptance record must state:

- Run ID, release SHA/image tag, environment and execution dates.
- Completed, blocked and excluded walkthrough steps.
- Open findings by severity and production-blocking status.
- Integration, infrastructure, legal and privacy evidence that remains external.
- Accepted pilot personas, modules, data classifications and operating constraints.
- Explicit `Accept`, `Accept with exclusions`, or `Reject` decision.
- Names, roles, dates and signatures/approval references for HR, security, privacy and product authorities.

Absence of a signed decision means the pilot is **not accepted**.
