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
- [x] Mandatory-training compliance + course catalogue — Shipped 2026-08-25. Spec:
      `docs/superpowers/specs/2026-08-25-mandatory-training-compliance-design.md`.
- [x] Succession/talent pools — Shipped 2026-08-25. Spec:
      `docs/superpowers/specs/2026-08-25-succession-talent-pools-design.md`.
- [x] Interview scheduling + panel scorecards + background/reference checks + external careers portal —
      Shipped 2026-08-25. Spec:
      `docs/superpowers/specs/2026-08-25-recruitment-interviews-careers-portal-design.md`.
- [x] Calibration/360 — Shipped 2026-08-26. Spec:
      `docs/superpowers/specs/2026-08-25-performance-calibration-360-design.md`.
- [x] Salary-review/bonus cycles + total-rewards statement — Shipped 2026-08-26. Spec:
      `docs/superpowers/specs/2026-08-26-salary-review-cycles-total-rewards-design.md`.
- [x] EE plan + consultation-forum records — Shipped 2026-08-26. Spec:
      `docs/superpowers/specs/2026-08-26-ee-plan-consultation-forum-design.md`.
- [ ] Real assessment-provider adapter

### C7 — UX / NFR
- [ ] Responsive + accessibility pass (ESS, liveness first); server-side pagination/search; broader bulk import/export; report builder + scheduled emails

