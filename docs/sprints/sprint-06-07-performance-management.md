[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

## Sprint 6–7 — Performance Management
**Goal:** Goal-setting and structured review cycles tied to `employees`.
**Status: done** (2026-08-12) — see `hcm/backend/performance/` (new app) and `hcm/frontend/src/pages/{ReviewCycles,Reviews,ReviewDetail}Page.tsx` + Goals/Feedback sections added to `EmployeeDetailPage.tsx`. Verified end-to-end in a real browser: hr_admin launches a cycle → employee submits a self-review → manager submits the manager-review on the same record → manager adds a goal and feedback from the employee's detail page → hr_admin sees completion stats update live, correctly isolated per cycle.

**Tasks:**
- [x] Goal-setting model (employee + manager) — `Goal` model + `GoalViewSet`; row-scoped via the existing `RowScopePermission`/`has_row_access` (self, or your manager, or hr_admin can set a goal for you)
- [x] Configurable review cycle (annual/biannual) with launch/track/close workflow — `ReviewCycle` model; `launch_review_cycle()` snapshots every currently-active employee into a `Review` row with `manager` fixed at launch time (a mid-cycle org change can't silently reassign who's reviewing whom), idempotent by construction (unique constraint + `get_or_create`)
- [x] Manager and self-review forms — `Review` model, one row per employee per cycle; self-review and manager-review sections are independently gated (only the reviewee can write the self section, only the review's recorded manager can write the manager section) via `ReviewSerializer.validate()`, with explicit `submit_self`/`submit_manager` actions stamping the submission timestamp the completion dashboard reads
- [x] Feedback capture (manager, peer) — `Feedback` model; creation is open to any authenticated employee (peer feedback crosses the org chart by definition) but `feedback_type` is computed server-side from the org chart at write time (`classify_feedback_type`), never trusted from client input; reading is row-scoped to the subject
- [x] Review completion tracking dashboard (target: 90%+ completion visibility) — folded into the Review Cycles page itself (`GET /review-cycles/{id}/completion/`) rather than a separate page, since the acceptance criterion is "launch... and see completion status" as one flow

**A real design tension, resolved consistently with recruitment's offer-pay exception:** RBAC-Roles.md says line_manager individually "sees own team's reviews/goals," but line_manager's generic Sensitive-tier grant is closed (aggregate-only, for demographics). `Review`/`Feedback` are therefore deliberately **not** run through the generic `TieredModelSerializer` — object-level row-scope (`RowScopePermission`) is the real access gate, the same pattern already used for `recruitment.Offer`'s pay fields. `Goal` (Internal-tier, not Sensitive) has no such conflict and does use the standard tiered path.

**Bug found and fixed during this sprint's own browser verification:** the Review detail page's "Submit" button called the `submit_self`/`submit_manager` action directly without first saving the in-progress rating/comments, so a natural "pick a rating, click Submit" flow 400'd with "Set a rating before submitting" — confusing, since the rating was visibly filled in on screen. Fixed by having Submit save-then-submit in one action; "Save draft" remains available separately for saving progress without submitting.

**Acceptance criteria:**
- [x] HR admin can launch a review cycle org-wide and see live completion status. — verified live: launched a new cycle, submitted a review through the browser, watched the completion percentage change on the Review Cycles page
- [x] Performance ratings are access-restricted per RBAC (not visible to all managers by default). — row-scope-gated (self / own reporting chain / hr_admin only); `performance/test_api.py::ReviewRowScopeAndWriteGatingTests`

**Verification:** `manage.py check --fail-level WARNING`, `makemigrations --check --dry-run`, and `manage.py test` all pass — 114/114 tests project-wide (85 prior + 29 new). Frontend `tsc -b && vite build` and `oxlint` both pass.

