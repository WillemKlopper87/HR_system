[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

## Sprint 4–5 — Recruitment / ATS
**Goal:** Requisition-to-hire pipeline feeding directly into `employees`.
**Status: done** (2026-08-12) — see `hcm/backend/recruitment/` (new app) and `hcm/frontend/src/pages/{Requisitions,Applicants,ApplicantDetail,RecruitmentDashboard}Page.tsx`. Verified end-to-end in a real browser as recruiter and hr_admin: create requisition → add applicant → capture consent → set demographics → move through the full pipeline → propose/approve/accept an offer → hire → confirmed the resulting `employees` row inherits the applicant's data with no re-entry.

**Tasks:**
- [x] Requisition creation and management (role, department, level, headcount) — `Requisition` model + `RequisitionViewSet`; status directly PATCHable, `opened_at`/`closed_at` auto-stamped on transition
- [x] Applicant model with pipeline stages (applied → screened → interview → offer → hired/rejected) — `Applicant.ALLOWED_TRANSITIONS` + `ApplicantStageEvent` audit trail (also what the dashboard's time-to-fill is computed from) + `recruitment/services.py::transition_applicant`
- [x] Applicant demographic capture with explicit consent flow — extended `rbac_audit.ConsentRecord` to a shared `employee`-or-`applicant` subject (Data-Dictionary.md's own documented shape, not a parallel table) rather than inventing recruitment-local consent tracking; `ApplicantSerializer.validate()` rejects writing race/gender/disability_status until `POST /applicants/{id}/consent/` has been called — enforced at the write path, not just hidden on read
- [x] Offer tracking and approval — `Offer` model + `OfferViewSet` (`approve`/`accept`/`decline` actions); `approve` enforces segregation of duties (RBAC-Roles.md standing rule 4: proposer ≠ approver), verified live in the browser (self-approve blocked with a clear error, a second user approves successfully)
- [x] Hire → automatic `employees` record creation (no re-entry) — `recruitment/services.py::_complete_hire()` calls the same `Employee.objects.hire()` Sprint 1 built for bulk import, so there's exactly one hire-to-record entry point system-wide; auto-generates the next employee number, fills the requisition (and stamps `closed_at`) once headcount is reached
- [x] Recruitment dashboard: pipeline status, time-to-fill, applicant demographics — `GET /api/v1/dashboards/recruitment/`; demographics small-cell-suppressed on the same basis as core_hr's headcount dashboard (`can_see_unsuppressed_aggregates`); demographic aggregates are consent-respecting by construction (a field can't hold a real value in the database without consent, so no extra filtering is needed at read time)

**Acceptance criteria:**
- [x] Given an applicant is marked "hired," when the record is saved, then a new `employees` row is created with no manual re-entry. — `recruitment/tests.py::HireAutomationTests`, plus live-browser confirmation (screenshot: newly hired employee's Identity + Current assignment cards match the applicant's captured data exactly)
- [x] Applicant demographic data is only visible per RBAC rules defined in Sprint 2. — consent-gated on top of (not instead of) the Sprint 2 field-tier grant; `recruitment/test_api.py::ApplicantConsentGatingTests`

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 85/85 tests project-wide (63 prior + 22 new). Frontend `tsc -b && vite build` and `oxlint` both pass. CI runs the same suite on every push.

