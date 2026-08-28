[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

# R1 — South African regulatory review backlog

**Created:** 2026-08-27  
**Source:** Review of the EE, B-BBEE, Skills Development and POPIA field guide against the current codebase.  
**Baseline reviewed:** `49da4ab` (`origin/master` matched local `HEAD`; working tree clean).

This is the source of truth for work arising from the regulatory review. It is separate from C1–C7 because
the field guide was supplied after that backlog was defined. A checked item means the capability exists; it
does not replace legal, EE-manager, verification-agency or SETA review of the resulting records and filings.

## Already delivered

- [x] Retain frozen `EEReport`/EEA2/EEA4 records for at least five years.
- [x] Seed all 18 EEA17 sectors and 2025–2030 sector targets; allow sector defaults to pre-fill an EE plan.
- [x] Remind HR/EE managers about the online EE reporting close and EEA14 notice deadline.
- [x] Report recruitment funnel progression by race, gender and disability status.
- [x] Add designated-group views to performance rating distribution.
- [x] Capture initial B-BBEE learning-programme category, agreement and evidence fields on training records.
- [x] Produce a B-BBEE management-control evidence schedule from the workforce profile.
- [x] Track probation periods, reviews, outcomes and completion rates by designated group.
- [x] Capture exit interviews and report departure reasons by designated group.

## P0 — Correct before production reliance

- [x] **Enforce probation-review row scope.** A line manager may create a review only for an employee in their
      current reporting chain; HR retains all-row access. Validate the selected `probation_period` during
      creation and add a negative test using another manager's report.
- [x] **Implement genuine employee countersignature for probation reviews.** Make `employee_signed_at`
      read-only; add an employee-only sign action that records actor, timestamp, review-content hash and audit
      event. A manager or HR user must not be able to manufacture the employee signature.
- [x] **Add protected training-evidence downloads.** Make the raw `evidence_file` response field write-only,
      expose an authenticated row-scoped download action, set the stored content type and filename safely, and
      log the download. Test own/team/all access plus an unrelated-employee denial.
- [x] **Close aggregate small-cell inference.** When a demographic cell is suppressed, do not return exact
      percentages or totals from which its value can be reconstructed. Apply one shared suppression policy to
      management control, probation, exit, recruitment and performance reports; add inference regression tests.

## P1 — Data integrity and defensible reporting

- [x] **Use historical employee versions for event reports.** Resolve demographics, department and level as at
      the probation outcome, exit, application stage, performance-period close or other relevant event date.
      Do not let a later employee update rewrite a historical compliance result.
- [x] **Define the performance-distribution unit.** Confirm whether the regulatory view is one final/calibrated
      employee score or individual KPI-element ratings. Rename the current result if KPI distribution is kept;
      otherwise report one final score band per employee. Test an agreement containing multiple KPIs.
- [x] **Harden probation dates and state transitions.** Require `end_date >= start_date`, prevent overlapping
      open periods for one employee, require an extension date later than the existing end date, and reject
      reviews outside the probation window unless an explicit override reason is captured.
- [x] **Validate exit-interview relationships.** When supplied, `employment_change` and `probation_period` must
      belong to the selected employee; define whether zero, one or both triggers are permitted and enforce it.
- [x] **Add browser coverage for new workflows.** Cover HR opening/deciding probation, the correct manager
      reviewing, the employee countersigning, HR capturing an exit interview, demographic dashboards, and a
      protected training-evidence download. Covered via `probation-workflow.spec.ts` (full probation lifecycle)
      and `regulatory-workflows.spec.ts` (protected evidence download row-scope, equity-dashboard suppression).
      HR capturing an exit interview has model/API-level coverage only, not a browser journey: `ExitInterviewsPage.tsx`
      does not yet expose the `employment_change`/`probation_period` trigger fields for a UI test to drive.
- [x] **Resolve frontend maintenance warnings.** Split non-component exports out of the two React context files,
      and introduce route-level code splitting for the oversized main and identity-verification bundles. Also
      added a shared `RouteErrorBoundary` around every lazy route and a build-time chunk-size budget
      (`vite.config.ts`) that fails the build on regression instead of relying on Vite's generic 500 kB warning.

## P1 — Statutory workflow foundation

- [ ] **Track EE filing, not only internal sign-off.** Add a submission record with form/report year, method,
      submitted timestamp, submitter, acknowledgement/reference, accepted/rejected/error state and evidence.
      Deadline reminders must stop only when the required filing has a defensible submitted/accepted state.
- [ ] **Track EEA14 inability notices.** Capture reasons, supporting evidence, submission date and acknowledgement;
      gate reminders against the actual notice state.
- [ ] **Track section 53 certificates.** Model EEA15/EEA16A–D application/outcome, issue and expiry dates,
      supporting evidence and renewal reminders. Do not infer a certificate merely from report sign-off.
- [ ] **Build formal EEA1 employee declarations.** Request a declaration from every employee, version the
      declaration text, preserve source/provenance and lawful basis, support refusal/not-disclosed handling, and
      treat disability non-disclosure and accommodation information as specially protected workflows.
- [ ] **Build the EEA12 analysis record.** Capture workforce profile, policies/practices, barriers, under- and
      over-representation findings, consultation evidence, owners and links into the EEA13 plan measures.
- [ ] **Create versioned regulatory obligations.** Store instrument/version/effective dates, due-date rule,
      responsible roles and evidence requirements. Use a South African business calendar rather than treating
      every Monday–Friday as a working day, and make reminder delivery idempotent for same-day reruns.

## P2 — Extended compliance evidence

- [ ] **B-BBEE Skills Development calculator and evidence pack.** First verify and version the applicable ICT
      Sector Code rules. Map categories A–G to their official meanings, distinguish employed/unemployed learners,
      calculate only from effective-dated rule tables, and export an auditable evidence pack. Never hard-code
      scorecard figures directly in service logic.
- [ ] **B-BBEE section 13G reporting pack.** Capture the organisation's applicable reporting basis, approval date,
      submission date and evidence; export the required schedule without claiming submission to the Commission.
- [ ] **WSP/ATR readiness workflow.** Confirm Sentech's SETA and current rules, then track consultation, committee
      approval, source data, evidence, submission and acknowledgement using configurable obligation dates.
- [ ] **Reasonable-accommodation register.** Separate disability identity from accommodation cases; restrict
      medical detail, track request/assessment/decision/review dates and expose only de-identified compliance
      totals outside the authorised case team.
- [ ] **Harassment intake and case controls.** Provide confidential intake, conflict-safe routing, restricted
      evidence, retaliation flags, outcome tracking and retention/legal-hold handling.
- [ ] **EE enforcement register.** Track EEA5/EEA6/EEA7 interactions, section 42 review evidence, undertakings,
      compliance orders, deadlines, owners and closure evidence.
- [ ] **Assigned EE managers as effective-dated records.** Support one or more assigned senior managers with
      appointment dates, scope, authority/resources and evidence while preserving the current report snapshot.

## Verification gate for every completed slice

- [ ] Add positive, negative, row-scope, field-tier, audit and historical-as-at backend tests appropriate to the slice.
- [ ] Run `manage.py check --fail-level WARNING` and `manage.py makemigrations --check --dry-run`.
- [ ] Run the affected apps' tests, then the complete backend suite.
- [ ] Run frontend lint, TypeScript build and production build for UI changes.
- [ ] Add or update Playwright coverage for user-visible workflows.
- [ ] Update `RBAC-Roles.md`, `Data-Dictionary.md`, API types/schema and `docs/SESSION-STATE.md` where applicable.
- [ ] Reconfirm current regulatory facts from primary official sources before implementing rules or deadlines.

