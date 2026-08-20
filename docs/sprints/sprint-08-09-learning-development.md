[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

## Sprint 8–9 — Learning & Development
**Goal:** Skills/certifications record per employee, org-wide skills visibility.
**Status: done** (2026-08-13) — see `hcm/backend/learning/` (new app) and the Skills/Certifications/Training sections added to `EmployeeDetailPage.tsx`, plus `SkillsInventoryPage.tsx` and `TeamDevelopmentPage.tsx`. Verified end-to-end in a real browser: manager adds a skill/certification/training record to a report → HR admin views the org-wide gap-analysis dashboard → downloads a real WSP/ATR CSV export.

**Tasks:**
- [x] Skills and certification model per employee — `Skill` (Public-tier catalog, hr_admin-managed), `EmployeeSkill`, `Certification`; row-scoped writes reuse the same self/manager/hr_admin pattern as `performance.Goal` (Sprint 6)
- [x] Training record tracking (completed/in-progress) — `TrainingRecord.status` (planned/in_progress/completed/cancelled) with `hours`/`cost`, sized for WSP/ATR reporting from the start (Data-Dictionary.md: "training_record (I — feeds WSP/ATR)")
- [x] Org-wide skills inventory report (gap analysis by department/level) — `GET /dashboards/learning/skills-inventory/` (hr_admin only): per-skill holder counts broken down by department and occupational level
- [x] Manager view of team development plans — `GET /dashboards/learning/team-development/`: a per-employee skills/certifications/training rollup across whatever the requester's row-scope covers, reusing `row_scoped_queryset` rather than a bespoke access model
- [x] **(added)** WSP/ATR (SETA) export — `GET /dashboards/learning/wsp-atr-export/`, a CSV joining training data to the EEA occupational-level/demographic fields a real WSP/ATR submission needs. This was flagged as a P1 gap in `Documentation-Review-and-Gap-Analysis.md` (gap C2 — "Skills Development Act reporting... absent from L&D sprints... add WSP/ATR export to Sprints 8-9 or it will be rebuilt in spreadsheets") with this exact sprint named as the fix; not part of the original sprint plan text, added per that recommendation

**Acceptance criteria:**
- [x] Skills inventory covers imported/entered employees with no duplicate skill entries per person. — enforced by a DB-level `UniqueConstraint(employee, skill)`, not just application logic; `learning/test_api.py::test_duplicate_skill_entry_is_rejected` confirms DRF surfaces it as a clean 400, not a 500

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 134/134 tests project-wide (114 prior + 20 new). Frontend `tsc -b && vite build` and `oxlint` both pass. Along the way, extracted the `Breakdown` chart component (previously duplicated near-identically in the headcount and recruitment dashboards) into a shared `components/Breakdown.tsx` now used by all three dashboards.

