# ADR-010: Performance agreements (KPI contracting) with in-app e-signature and delegated signing

**Status:** Proposed (2026-08-18) — design in `docs/superpowers/specs/2026-08-18-kpi-contracting-design.md`

## Context
Individual scorecards are contracted each financial year (1 Apr–31 Mar) in an Excel template between each staff
member and their Head/executive: Objective → KPA → KPI rows, weight per KPI (Σ = 1.00), 1–5 rating with a target
written per level, Q2 and Q4 reviews, PDP sheet, employee-then-Head signatures; HR receives the result. Evidence
lives on individual PCs; reminders are ad-hoc corporate emails; revisions are tracked by hand. The `performance`
app has only a single-rating `Review` per cycle.

## Decision
- Extend the existing `performance` app in place (no new app; `ReviewCycle` becomes the period) with versioned
  templates, agreements/elements mirroring the scorecard grid, per-KPI evidence (file or OneDrive/Teams link),
  strict employee→Head signing per stage, and archived PDF snapshots.
- Signature = ordinary electronic signature under the ECT Act: click-to-sign with password re-authentication (or
  ADR-009 TOTP step-up when the template requires it), immutable `AgreementSignature` carrying the sha256 of the
  PDF signed, actor, time, method, IP/UA; every signature audit-logged. No external e-sign vendor.
- Delegated signing only through an explicit, dated `SigningDelegation` created by the Head or hr_admin; the
  record shows "signed by X acting for Y". HR is a recipient/archive, never a signatory.
- Ratings/scores are Sensitive-tier gated by row-scope + an explicit permission class (same reasoning as `Review`).

## Consequences
- Three sprints (PC-1 contracting+reminders, PC-2 reviews+evidence+scoring, PC-3 archive+dashboards); legacy
  `Review` derived from agreements, then retired.
- Requires Celery (beat) — forces the H1 decision to wire it. `ImprovementPlan` is a stub until HR describes it.
- Executive form variants, moderation and matrix reporting are explicitly out of scope until requested.
