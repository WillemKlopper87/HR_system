# HR_system — Consolidated Roadmap (everything outstanding, sequenced)

**Written:** 2026-08-18 · **Inputs:** `NEXT_AGENT_BRIEF.md` (§3 do-differently, §4 defects D1–D11, §5 deferred, §6
Sprint 16–17 plan, §7 missing capabilities), `KPI-Contracting-Investigation.md` (PC-0…PC-3),
`docs/superpowers/specs/2026-08-18-kpi-contracting-design.md`, ADR-010/011.
**How to use:** each row below is one autonomous sprint loop (build → `manage.py test` → real-browser verify across
roles → update `Sprint-Plan-HCM-System.md` + `hcm/README.md` → commit → push → next). The matching sprint headers
with `[ ]` tasks are appended to `Sprint-Plan-HCM-System.md` ("Backlog additions 2026-08-18") so the normal loop can
execute them; this file holds the reasoning, ordering and dependencies.

Legend: **H** = hardening (was Sprint 16–17) · **PC** = performance/KPI contracting · **X** = collab-platform work
(other repo) · **C** = capability from brief §7. Sizes are relative (S ≈ half a loop, M ≈ one, L ≈ one and a half).

---

## 0. Ordering principles

1. **Unblock first, then build.** Celery, throttling, Postgres-in-CI, lock file, 401 handling and the test harness
   are cheap and every later sprint leans on them — they go first (H1, H2).
2. **KPI contracting is the next product increment** and its reminder engine is the reason to wire Celery + collab
   integration properly, so PC-0 lands right after H2 and PC-1..3 follow back-to-back.
3. **Notifications and the audit viewer are cross-cutting** (brief §7.1 #1/#2); notifications ship in the same
   sprint as PC-1's reminders (one mechanism, two consumers), the audit viewer in H3.
4. **UAT/sign-off needs people** — it is a rolling gate after H3 and again after PC-3, not a sprint the agent can close.
5. §7 capabilities beyond the top picks are sequenced by dependency and value; they can be reordered by the user at
   any time without breaking earlier sprints.

## 1. The sequence

| # | Sprint | Scope (what gets built) | Closes | Size | Depends on |
|---|---|---|---|---|---|
| **H1** ✅ done 2026-08-18 | Platform foundations | `config/celery.py` + beat + first task (RetentionRule executor); DRF throttling on login + TOTP enroll/confirm/challenge (+429 tests); Postgres service job in `hcm-ci.yml`; `requirements.lock` (pip-compile) + CI uses it; global 401 handler in `api/client.ts` → clear auth + redirect; docker-compose: fix worker, add `frontend` (nginx serving `dist/` + `/api` proxy + `MEDIA` via authenticated download only); ADR-007/008/009 files in `adr/`; fix `tiers.py:80` comment; reword README tiering rule; replace `hcm/frontend/README.md`; `.gitignore` for personal files (done) | D1 D2 D3 D5 D6 D8 · §3.2 §3.4 §3.5 §3.7 §3.8 §3.10 | L | — |
| **H2** ✅ done 2026-08-18 (ZAP triage → H3) | Test harness + frontend consolidation | Playwright suite (`hcm/frontend/e2e/`, one spec per module, seeded demo logins, `npm test`, CI job); shared `useApiQuery`/`useMutation` hook + migrate list pages; dedupe `Field`, `formatZAR`, nav config array (`NavItem`); exhaustive RBAC matrix test (every viewset × every role × CRUD ↔ `RBAC-Roles.md`); import-linter (or a `manage.py check` rule) for "no peer imports" with test carve-out; upload content-type sniff + clean 400 for policies (D4); ZAP Low/Info triage | D4 D9 D10 D11 · §3.1 §3.3 · S16 "regression suite", "RBAC pen-test" | L | H1 |
| **X0** ✅ done 2026-08-18 (collab `23d4f05`) | Collab platform: integration surface | Service-account/API-key auth for machine callers; `WorkItem.external_ref` + `source` (+ unique per source); `GET /work-items?external_ref=`; upsert semantics; announcement create/publish usable by the service account; optional outbound webhook on work-item status change; identity lookup by work email. Also fix the collab CI (per its own brief) so this ships green | ADR-011 prerequisites | M | — (other repo; can run parallel to H1/H2) |
| **PC-0** ✅ done 2026-08-18 | HR → collab adapter | `integrations/collab.py` (create/close work items, publish announcements, retry/backoff), `Employee.collab_user_id` (+ lookup command by email), Celery task wrapper, feature flag `COLLAB_ENABLED`, contract tests against a recorded collab API; ADR-011 committed | ADR-011 · §7.1 #1 (delivery half) | M | H1, X0 |
| **PC-1** ✅ done 2026-08-18 (`6bcb396`) | Performance periods, templates, contracting, reminders, delegation | `PerformancePeriod` (FY 1 Apr–31 Mar, phases + reminder offsets); `AgreementTemplate/Section/Element` (versioned, targeted, `level_descriptors {1..5}`, `metric`, `evidence_required`); `PerformanceAgreement/Element/PDPItem`, weight = 1.00 validation, revision counter; state machine draft→submitted→returned/approved→employee_signed→head_signed(agreed) with **strict order**; click-to-sign + password re-auth, `AgreementSignature` immutable with PDF `sha256`; `SigningDelegation`; PDF snapshot reproducing the scorecard grid (reportlab); scheduler job (beat) computing outstanding people per phase → collab work items/critical announcement/Head digest via PC-0; hr_admin completion dashboard; frontend `/my-performance`, `/team-performance`, `/performance/periods`, `/performance/templates` | ADR-010 · PC-1 · §7.1 #1 (scheduling half) | L | PC-0 (degrades gracefully if `COLLAB_ENABLED=0`) |
| **PC-2** ✅ done 2026-08-19 (`96c0c9c`) | Reviews, evidence, scoring | Q2 stage (target note + employee/manager comments, employee→Head sign) and Q4 stage (rating 1–5 per KPI, score = weight×rating, Σ = final score, comments, sign); `EvidenceItem` (file **or** OneDrive/Teams link) per KPI × stage, "no evidence" marker, `evidence_required` enforcement, "added after sign-off" stamp; amendments as new revision (re-sign); HR-attention flag when final (or per-KPI, configurable) < 3; derive legacy `Review` ratings from the agreement so existing pages keep working; reminders for Q2/Q4 reuse PC-1's engine | PC-2 | L | PC-1 |
| **PC-3** ✅ done 2026-08-19 (`794681e`) | Archive, dashboards, outcomes | Period close/archive (final signed PDF + evidence manifest per agreement, hashed); auditor pull of any signed PDF + signature trail; dashboards (completion by division, rating distribution with small-cell suppression as EE does), Head team view; `ImprovementPlan` **stub** (owner, reasons, actions, review dates, outcome) behind the HR-attention flag; optional: final band → `compensation.CompProposal` draft, PDP items → `learning.TrainingRecord(REQUESTED)`; retire or hide legacy Reviews pages | PC-3 | M | PC-2 |
| **H3** 🔶 in progress 2026-08-19 (`5e94d85`, audit-log `55684de`, ops `b4621fe`, OpenAPI `a16f11f`, data-quality + EEA validation pending commit) | Cross-cutting HR platform | Email adapter (SMTP/Graph) + `Notification` model + in-app bell (consumers: PC reminders, comp approvals, review launch, policy publish, liveness flag, EE sign-off) ✅ done; **audit-log API + viewer** for `auditor` (filter actor/subject/action/tier/date, CSV) ✅ done; **org-wide data-quality registry** (built-in core_hr checks + `performance` overdue-stage + `compensation` stale-proposal handlers) ✅ done; **EEA export cell-by-cell validation** vs `EEA-Form-Spec-Notes.md` (`validate_report_data` + `/validate/` action, browser-verified) ✅ done; `LOGGING` + Sentry hook + `/readyz`; backup/restore runbook (Postgres + media) ✅ done; Sprint-0 checkbox reconciliation, sprint-plan split into `docs/sprints/*.md` — not started; OpenAPI (`drf-spectacular`) + generated TS types replacing hand-written `api/types.ts` 🔶 schema/docs/codegen pipeline done, the actual `api/types.ts` replacement is not | §7.1 #1 #2 #6 #7 #8 · S16 "DQ org-wide", "EEA validation" · §3.9 §3.10 | L | H2 (PC-1 for the reminder consumer) |
| **UAT-1** | Rolling gate (people) | Walkthrough script from sprint-plan verification paragraphs; HR/talent/EE stakeholder UAT; security/compliance sign-off; findings feed a fix sprint | S16–17 exit criteria | — | H3, PC-3 |
| **C1** | Establishment & lifecycle | `Position` model (approved vs filled posts, post number, vacancy rate; requisitions tied to a vacant post); `contract_end_date` / `probation_end_date` + reminders (via H3/PC-1 engine); onboarding/offboarding checklists (termination cascades: role assignments, liveness enrolment, collab account flag) | §7.2 #10 #11 #12 | L | H3 |
| **C2** | Employee documents & POPIA rights | `EmployeeDocument` (tiered, consent-aware, authenticated download — same pattern as policies/evidence); qualifications feeding WSP/ATR + EE; dependants/emergency contacts; data-subject export/erasure request workflow; RetentionRule scopes extended to documents/evidence | §7.2 #13 #14 · §7.1 #9 | M | H1 (retention job) |
| **C3** | Identity & integrations | OIDC/Entra SSO (ADR-004; align identity mapping with collab/Keycloak → single IdP decides `collab_user_id` mapping); SAP payroll read-only pull (ADR-006/A10) replacing CSV import; leave read-only mirror from SAP (§7.3 #17); field-level step-up for `recruitment.Offer` pay fields (D7) | D7 · §7.1 #4 #5 · §7.3 #17 | L | H3 (needs IT/SAP counterparts) |
| **C4** | Generic delegation & approvals | Generalise `SigningDelegation` into `Delegation(scope)` honoured by `has_row_access` (acting manager for reviews, goals, team requests, comp approvals); "my approvals" inbox on top of H3 notifications | §7.1 #3 | M | PC-1, H3 |
| **C5** | Labour relations | Disciplinary & grievance case management (warnings, hearings, outcomes, CCMA referral), linked to `ImprovementPlan` (PC-3) and feeding EEA2 workforce-movement; consent/tiering as Sensitive | §7.3 #16 | L | PC-3, C1 |
| **C6** | Talent depth (pick per demand) | Succession/talent pools + career paths (on `Position`); recruitment interview scheduling + panel scorecards + external careers portal; performance calibration/moderation + 360; mandatory-training compliance + course catalogue; salary-review/bonus cycles + total-rewards statement; EE plan + consultation-forum records; real assessment-provider adapter | §7.3 #18–24 | L each | C1, PC-3 |
| **C7** | UX / NFR | Responsive + accessibility pass (ESS + liveness first); server-side pagination/search; broader bulk import/export; report builder + scheduled emails; multilingual (if ever) | §7.4 #25–28 | M | H2 |

## 2. Critical path

`H1 → H2 → (X0 ∥) → PC-0 → PC-1 → PC-2 → PC-3 → H3 → UAT-1`, then C1 → C2/C3/C4 in any order, C5/C6/C7 by demand.
Roughly 9 loops to reach a UAT-ready system with KPI contracting live; the C-series is open-ended by design
(scope is "open/rolling" per Sprint-0 A9).

## 3. Explicit assumptions carried into the KPI work (from the investigation; change here if wrong)

- FY 1 April → 31 March; two review stages (Q2, Q4); no moderation committee; rating 1–5, 3 = fully effective,
  5 = exceptional; band labels are a suggestion until the policy is quoted.
- Signing order employee → Head, strict; HR is recipient/archive, not signatory; delegation only via an explicit
  `SigningDelegation` created by the Head or hr_admin.
- Evidence optional-but-visible by default (`evidence_required` per template); file or OneDrive/Teams link.
- Click-to-sign + password re-auth is the default signature method; TOTP step-up (ADR-009) selectable per template.
- Collab platform is outbound-only and best-effort: if it is unreachable, contracting still opens and reminders retry.
- One scorecard shape for all levels until an executive variant is provided.

## 4. What is *not* on this roadmap (deliberately)

- Policy chatbot / RAG / LLM (ADR-008) — waits for a vendor + abuse-prevention sign-off.
- Building leave/time & attendance (stays in SAP; mirror only).
- Any external e-signature vendor (not required by the ECT Act for these documents).
