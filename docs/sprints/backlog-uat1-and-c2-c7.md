[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

### UAT-1 — Rolling gate (needs people)
- [ ] Walkthrough script from the verification paragraphs; HR/talent/EE stakeholder UAT; security/compliance sign-off; fix sprint from findings

### C2 — Employee documents & POPIA rights — Shipped 2026-08-25
Spec: `docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md`.
- [x] `EmployeeDocument` (tiered, consent-aware, authenticated download); qualifications → WSP/ATR + EE
- [x] Dependants / emergency contacts; data-subject export/erasure workflow; retention scopes for documents/evidence

### C3 — Identity & integrations
- [ ] OIDC/Entra SSO (ADR-004), single-IdP identity mapping with collab
- [ ] SAP payroll read-only pull (ADR-006/A10); leave read-only mirror; field-level step-up for `recruitment.Offer` pay fields

### C4 — Generic delegation & approvals
- [ ] Generalise `SigningDelegation` → `Delegation(scope)` honoured by `has_row_access`; "my approvals" inbox

### C5 — Labour relations
- [ ] Disciplinary & grievance cases (warnings, hearings, outcomes, CCMA), linked to `ImprovementPlan`, feeding EEA2 movements

### C6 — Talent depth (per demand)
- [ ] Succession/talent pools; interview scheduling + external careers portal; calibration/360; mandatory-training compliance + catalogue; salary-review/bonus cycles + total-rewards; EE plan + consultation records; real assessment-provider adapter

### C7 — UX / NFR
- [ ] Responsive + accessibility pass (ESS, liveness first); server-side pagination/search; broader bulk import/export; report builder + scheduled emails

