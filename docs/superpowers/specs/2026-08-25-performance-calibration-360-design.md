# Design Spec — Performance Calibration/Moderation + 360° Feedback

**Date:** 2026-08-25 · **Status:** implemented · **Gap:** `NEXT_AGENT_BRIEF.md` §7.3 #20 (the calibration/360 half —
PDPs are already built, `performance/models/agreements.py::PDPItem`, untouched here) · **Source material:**
`docs/superpowers/specs/2026-08-18-kpi-contracting-design.md` (PC-1..PC-3, whose §1 non-goals explicitly deferred
"moderation committee" — this spec is the thing that deferral pointed at), `ROADMAP-2026-08.md`'s PC-3 row
(rating-distribution dashboard, the optional CompProposal linkage), `RBAC-Roles.md`, `docs/superpowers/specs/
2026-08-25-succession-talent-pools-design.md` (precedent for a hard visibility/anonymity call).

## 1. The problem

The KPI-contracting system (PC-1..PC-3) takes an agreement all the way to `FINAL_SIGNED`/`ARCHIVED` on nothing but
one employee and one Head's joint judgement. Two things the brief flags as missing:

1. **No consistency check across a cohort before scores are treated as final.** One Head's "3" and another Head's
   "3" for a comparable role can mean different things; nothing catches that before the score feeds into whatever
   consumes `final_score` (currently just the legacy `Review` mirror and the rating-distribution dashboard, but the
   ROADMAP-2026-08.md PC-3 row also names an optional comp-proposal linkage this could eventually feed).
2. **No multi-rater (360°) input.** Reviews are strictly self+manager (`AgreementElement.final_employee_comment`/
   `final_head_comment`, or the legacy `Review.self_rating`/`manager_rating`). Nothing captures how peers or
   direct reports see someone's collaboration/communication/reliability — signal a KPI-only scorecard structurally
   cannot carry.

Confirmed absent by grep (`calibrat`, `moderat`, `360`) before starting — the only hits were the KPI-contracting
spec's own "non-goal" line and `NEXT_AGENT_BRIEF.md` itself.

## 2. Structural decisions

### 2.1 Both features live in `performance`, as siblings of `agreements.py`, not a new app

Unlike succession (own app — new domain object, new audience) or recruitment's C6 slice (extended an existing app
that already owned the parent objects), calibration and 360 are both *about* a `PerformanceAgreement*` — they read
its `final_score`/`status`, and 360's whole reason for existing is to feed the Head's read of an agreement.
Splitting them into a new app would mean importing `PerformanceAgreement` across an app boundary for the one thing
both features fundamentally need to reference, for no audience or lifecycle reason to justify it. Two new model
modules keep `agreements.py` from becoming unreadably long: `performance/models/calibration.py` (`CalibrationSession`,
`CalibrationAdjustment`) and `performance/models/feedback360.py` (`Feedback360Request`, `Feedback360Rater`,
`Feedback360Response`).

### 2.2 Calibration: scoped by department, matching the dashboard that already exists

The brief asks whether the cohort is department, a shared Head, or org-wide. `views_agreements.py::rating_distribution`
(PC-3) already answers this question for the closest existing feature — it groups by `division` (an agreement's
employee's current department) with small-cell suppression, precisely because "does this cohort's rating spread look
consistent" is the question calibration exists to answer. Reusing that exact grouping unit means a calibration
session's candidate list and the dashboard the committee would actually look at before meeting are the same shape.
A shared-Head cohort was considered and rejected: `PerformanceAgreement.head` is snapshotted per-employee at
agreement-creation time (so a Head's own "cohort" drifts across the year as org changes happen) and a Head typically
only has a handful of direct reports — too small a sample for the consistency check calibration exists to run,
whereas a department is stable and large enough to be meaningful. `CalibrationSession.department` is nullable
(blank = org-wide session, following `AgreementTemplate`'s own "empty targeting = everyone" precedent) so an
org-wide moderation round is still possible without inventing a second model shape for it.

### 2.3 Calibration is hr_admin recording an offline outcome, not a live workflow

Per the brief's explicit steer: a single hr_admin recording what a committee decided after an offline meeting is
the realistic shape (`Course`/`CriticalPost`/`ChecklistTemplate` are the standing single-actor-authorship precedent
in this codebase for exactly this kind of workforce-planning record — hr_admin authors directly, no second
approver). Building live multi-party consensus tooling for a process that in practice is a meeting with minutes
would be speculative scope for no named consumer. `CalibrationSession.participants_note` is a free-text field for
"who was in the room" — not a structured attendee list with its own RSVP/approval flow.

### 2.4 Calibration never rewrites a signed score silently — three independent audit layers, no re-signature

The guardrail is explicit: no quiet overwrite of `final_score`. Three things happen together, in one
`transaction.atomic` block, whenever a calibration adjustment changes a score:

1. A new `CalibrationAdjustment` row is created — **immutable, create-only** (no update/delete route in the API,
   the same shape `AgreementSignature` already uses for "no update/delete path exists"). It carries
   `previous_score`, `new_score` (nullable — null means "reviewed, no change needed", so a session can show it
   reviewed every agreement in the cohort even where nothing moved), `reason` (required on every row, changed or
   not — mirrors `return_agreement`/`amend_agreement`'s "reason required" pattern), `adjusted_by`, and a timestamp.
2. `PerformanceAgreement.final_score`/`hr_attention`/`hr_attention_reason` are updated directly — and
   `PerformanceAgreement` already carries `history = HistoricalRecords()` (PC-1), with
   `simple_history.middleware.HistoryRequestMiddleware` already installed (`config/settings.py`), so this write is
   automatically captured with the acting user, before/after values, and a timestamp in the existing history table
   with zero new infrastructure.
3. `log_access(..., field_tier=SENSITIVE)` records the change in the existing audit log, same as every other
   sensitive mutation in this module.

**Does an adjustment trigger re-signature?** No — and this is a deliberate, considered call, not the path of least
resistance. `amend_agreement` (PC-1's existing "reopen a contracted agreement" primitive) exists for exactly one
kind of event: the employee and Head jointly deciding to revisit what they agreed. Calibration is a categorically
different event — an HR/committee act of *cross-cohort consistency*, not a renegotiation between the two original
signatories. Running a calibration tweak through `amend_agreement` would misrepresent it as the employee and Head
reopening their own agreement (revision+1, status back to `DRAFT`, forcing the entire submit → approve → sign chain
to run again for what is often a small numeric nudge for consistency), and would leave a calibrated agreement sitting
in an unfinished, unsigned state for a potentially unbounded stretch if either party is slow to re-engage —
undermining PC-3's whole point of actually being able to archive a finished year. It would also, per real HR
practice, be procedurally backwards: calibration happens *because* the individual sign-off already happened: it's a
second, higher-level check layered on top, not a do-over of the first one.

The counter-argument the brief itself raises — this system's philosophy elsewhere is "amendments as new revision,
re-sign" — is taken seriously, not waved away: what makes that pattern right for `amend_agreement` (a substantive
content change either party might reasonably want to renegotiate) is exactly what's absent here (a numeric,
committee-level consistency correction). The original `AgreementSignature`/`AgreementDocument` rows for the FINAL
stage are left completely untouched — they remain the true, hashed, provable record of *what was mutually agreed
and signed at that moment* — the calibration record sits **alongside**
that history, not over it. Fairness/CCMA exposure is addressed by transparency instead of a re-sign gate: the
reason is mandatory on every row (even "no change"), the adjustment is visible to the employee and their Head (not
just hr_admin — §2.6), and the full "what it was signed at, what it became, why, by whom, when" trail is
reconstructable end to end. If a future legal review decides fairness specifically requires re-consent, that's a
one-line change to have `record_calibration_outcome` call `amend_agreement` instead — the audit trail this design
already produces doesn't need to change either way.

### 2.5 Eligibility: only `FINAL_SIGNED`/`ARCHIVED` agreements can be calibrated

Per the brief: calibration reviews *finalized* scores. Gating creation to
`agreement.status in (FINAL_SIGNED, ARCHIVED)` means calibration can never race an agreement still being contracted
or reviewed — the KPI ratings that produced `final_score` are frozen (both signatures exist) before a committee ever
sees the number.

### 2.6 Calibration read access: hr_admin/auditor for the session; the agreement's own audience for one row

`CalibrationSession`/its full adjustment list (a named cohort's whole distribution) is `hr_admin`/`auditor` only —
the same "hr_admin + auditor only, no self/team browsing" precedent succession's `SuccessionCandidate` established
(spec §2.6/§5.2 there): a department-wide committee record is a comparative judgement about a group of named
individuals, the same risk shape as a successor list, just at cohort scale instead of one critical post. A single
`CalibrationAdjustment` row, however, is also reachable through the **existing** `PerformanceAgreementPermission`
gate as a nested field on `PerformanceAgreementSerializer` — whoever can already view the agreement (the employee
themself, their Head/delegate, hr_admin, auditor — `can_view_agreement`) sees whether and why it was calibrated,
exactly like `return_reason`/`amendment_reason` already ride along on the same object. This is the concrete
expression of "visible either way" from §2.4: the subject is never left wondering why their number moved, but they
can't browse their department's committee proceedings for everyone else.

### 2.7 360° feedback attaches to `PerformanceAgreement`, not the legacy `Feedback` model — and deliberately does not copy its openness

The brief asks this explicitly. `models/cycles.py::Feedback` is a real, working precedent for multi-rater input in
this codebase (creation open to any authenticated employee, `feedback_type` derived server-side from the org chart
via `classify_feedback_type`, reading row-scoped to the subject) — but it is free-text only and, critically, **fully
open authorship**: anyone can write feedback about anyone, with no nomination or approval step. That openness is
defensible for what `Feedback` is (a private, unrated note a colleague chooses to leave) and wrong for what 360
needs to be: **structured, rated input that a Head reads alongside a KPI scorecard when forming a real assessment.**
Open free-for-all authorship on something that carries ratings invites both spam and coordinated pile-on/inflation
risk with no gate at all. `Feedback360Request`/`Rater`/`Response` are new models (§4), explicitly not an extension
of `Feedback` — the two coexist; `Feedback` is untouched.

### 2.8 Structure: fixed 3-criterion 1–5 vocabulary, matching `InterviewScorecard`'s precedent exactly

`recruitment.InterviewScorecard` (shipped this session cycle) already answered "how do we structure a rated,
multi-rater input in this codebase" for panel interviews: a small, fixed (not per-requisition-configurable) set of
1–5 criteria plus free text plus a summary judgement. 360 reuses that shape rather than inventing a second one:
`collaboration_rating` / `communication_rating` / `reliability_rating` (1–5, the same scale `performance` already
uses — `DEFAULT_RATING_SCALE`), plus `strengths` and `development_areas` as two separate free-text fields rather
than one blob — the PDP-linkage rationale (development areas is exactly the kind of input a future PDP conversation
would want to draw on) makes the split worth the one extra field, and it costs nothing to build. Per-agreement
configurable criteria was considered and rejected for the same reason `InterviewScorecard`'s spec rejected it:
unjustified complexity for a feature this session has no evidence needs it.

### 2.9 Who can be nominated as a rater: self + manager automatic, peers/reports nominated and Head/hr_admin-approved

Real 360 practice (and the brief's own steer) is nomination-with-sign-off, not `Feedback`'s free-for-all — this
input can shape a real assessment, unlike a private note. Concretely:

- **`self`** and **`manager`** rater slots are created automatically and pre-`APPROVED` the moment a
  `Feedback360Request` opens (the employee always self-assesses; the snapshotted Head — or an active
  `SigningDelegation` if the Head can't act — is definitionally included, no nomination needed).
- **`peer`**/**`direct_report`** slots start `PENDING_APPROVAL`. Either the employee or their Head/hr_admin may
  nominate a rater; `relationship` is derived **server-side** from the org chart at nomination time (same
  reasoning as `classify_feedback_type` — never trusted from client input), and a nomination that resolves to
  `self`/`manager` (already automatic) is rejected outright rather than silently duplicated. Approval — turning a
  nomination into an active, response-accepting slot — is `is_head_of(...)` or `is_admin(...)` only, the exact
  same authority test every other agreement-side action in this module already uses.
- A manager-nominates-only or fully-open model were both considered: fully open was rejected for the reason in
  §2.7; manager-only nomination was rejected because the subject is usually the person with the clearest view of
  who they actually work with closely enough to give useful 360 input — the same "who's closest to the truth"
  reasoning succession's spec used when it *didn't* build a manager-only nomination gate for critical-post
  successors (2026-08-25-succession-talent-pools-design.md §2.6) — the approval step is what keeps this from being
  `Feedback`'s free-for-all, not restricting who may propose a name in the first place.

`direct_report` is classified as "anywhere below the subject in today's reporting chain" (`is_in_reporting_chain
(employee, nominee)`), not strictly one level down — matching `is_head_of`'s own "anyone above ... in today's
reporting chain" breadth for the mirror-image relationship, and because a skip-level report's view of a manager is
still direct-report-shaped input, not peer-shaped.

### 2.10 Visibility/anonymity — the load-bearing decision

This is the one call in this feature where getting it wrong genuinely breaks the feature, not just style. The
brief names the industry-standard answer and this spec adopts it, with the specific thresholds and scope spelled
out:

**To the Head (`is_head_of`), hr_admin, and auditor: every response, fully attributed, always.** They are
synthesizing input into a real decision, not forming an independent first impression that peer attribution could
bias — the same "aggregating for a decision, not an independent judgement" reasoning
`InterviewScorecardSerializer.to_representation` already uses to give recruiter/hr_admin unmasked scorecards
immediately. A Head who spots a concerning pattern from a specific rater needs to know who said it to act on it
(e.g. a direct report describing a real problem) — full attribution to this audience is a feature, not an oversight.

**To the subject (the employee the round is about):**
- Their own **self** response: obviously visible, it's theirs.
- The **manager/Head**'s response: fully attributed, both ratings and free text — this is not a new disclosure risk,
  since the Head's `final_head_comment` on the same agreement is already visible to the employee elsewhere in this
  exact system; a 360 response from the same person carries no different exposure.
- **Peer and direct-report** responses: **numeric ratings only, pooled into a per-relationship-type average, and
  only once at least 3 responses exist in that bucket** — never individually attributed, and **never with free
  text at all** (not even pooled/paraphrased). Below the 3-response floor, the subject sees "not enough responses
  yet to summarise anonymously" instead of a number.

Reasoning, in order of how consequential each part is:

- **Free text to the subject is refused outright for peer/direct-report input, not just anonymized.** Anonymizing
  a name is easy; anonymizing a sentence is not — writing style, phrasing, and the specific thing raised can
  re-identify a rater to the subject even with the byline stripped, especially in a department small enough that
  everyone already knows who works closely with whom. Rather than attempt a paraphrase/pooling scheme that would
  still leak, free text from this rater group simply never reaches the subject at all; it reaches the Head/hr_admin
  (fully attributed, per above), who is the person positioned to relay anything specific through a real
  conversation, using their own judgement about what to attribute and what to protect — the same role a manager
  already plays when synthesizing team input in any real HR process.
- **A 3-response floor per bucket, not the dashboard's existing 5.** `views_agreements.py::SMALL_CELL_THRESHOLD = 5`
  exists to protect a demographic cell inside an org-wide/departmental aggregate from re-identification — a
  different risk shape and scale from a 360 round, whose realistic rater pool per relationship type is 2–6 people
  by construction (you don't nominate twenty peers). Reusing 5 verbatim would mean peer/direct-report feedback
  almost never clears the bar, making the feature look broken by default rather than protective; 3 is the smallest
  N where a subject genuinely cannot back-solve one rater's answer from the pool (at n=2, subtracting your own
  known data point — if you're in the pool — or the one other number you can infer fully recovers the other
  rater's score). A new module constant, `FEEDBACK_360_MIN_RESPONSES_FOR_AGGREGATE = 3`, is defined next to
  `SMALL_CELL_THRESHOLD` with this reasoning inline, deliberately not reusing the same name/value.
- **Peer and direct-report buckets are kept separate, not pooled together, even though pooling would clear the
  3-response floor sooner.** They carry different meaning (a report's view of you as a manager vs. a colleague's
  view of you as a peer) and collapsing them would blur exactly the signal a real 360 process values. The cost —
  direct-report feedback, typically the smallest and most retaliation-sensitive group, may stay permanently
  suppressed at small team sizes — is accepted deliberately: protecting anonymity for the group most likely to fear
  retaliation is the point, even at the cost of that group's input reaching the subject less often. hr_admin/Head
  still see it fully attributed regardless of bucket size, so it is never lost, only withheld from the one audience
  where anonymity matters.
- **No blind-review-style sequencing among raters (InterviewScorecard's "hidden until you submit your own" gate)
  was considered and rejected as the wrong pattern here.** That mechanism protects against one rater's answer
  anchoring another's *while both are deciding the same thing under time pressure in a live process* (a panel
  interview). 360 raters here never see each other's responses at all, ever, regardless of submission order — only
  the Head/hr_admin sees individual attribution, so there is no anchoring surface between raters to protect in the
  first place; the actual protection this feature needs is anonymity from the *subject*, which the aggregate-only
  rule above already provides.

### 2.11 360 is qualitative context, never an input to `final_score`

Per the brief's own default and guardrail: `final_score` is `Σ(weight × rating)` over KPI elements
(`_finalize_scoring`), an already-shipped, tested calculation with real downstream consumers (the legacy `Review`
mirror, the rating-distribution dashboard). Folding a differently-scaled, differently-sourced 360 number into that
formula would silently change what `final_score` has always meant, for every historical agreement that already has
one. `Feedback360Request`/`Response` never write to `PerformanceAgreement.final_score` anywhere in the service
layer — they're read-only context surfaced next to the KPI scorecard (§2.6-style: an embedded field on the
agreement read, gated the same way), never summed into it. A future PDP/comp-cycle feature is free to *read* the
aggregate the same way `performance/queries.py::latest_final_score` already lets `succession` read `final_score`
today, without this change needing to touch the scoring formula at all.

### 2.12 Data-quality check: final-signed agreement, no calibration session opened for its period

Per the brief's steer (§8 of the original brief, "if useful"). `performance/data_quality.py` gains
`missing_calibration_handler`, registered under a new `DataQualityException.ExceptionType.PERFORMANCE_NO_CALIBRATION`
— same shape as the existing `overdue_agreement_handler`: once a period's FINAL phase due date has passed and the
period has **no** `CalibrationSession` at all yet, every `FINAL_SIGNED` agreement in it is flagged per-employee
(the registry's `Handler` type yields `(employee, detail)` tuples, so a period-level gap is still expressed
per-agreement the same way the overdue-stage check already is).

### 2.13 The optional `CompProposal` linkage: confirmed not built, and left out of scope here

`ROADMAP-2026-08.md`'s PC-3 row names "optional: final band → `compensation.CompProposal` draft" as unbuilt —
confirmed by grep (no `compensation` import anywhere in `performance/`, and `compensation` has no `queries.py` read
seam a calibration-adjusted score could flow through without a direct cross-app model import, which the module
boundary rules forbid). It stays out of scope for this slice: nothing in the brief for *this* task asks for it, and
building a one-way write seam from `performance` into `compensation` (`CompProposal` has no existing read-only
seam pattern to extend, unlike `learning`/`performance` which already have `queries.py`) is a new piece of
cross-module plumbing that deserves its own design decision (what triggers it — every final-signed agreement, or
only calibrated ones? does an *adjustment* re-trigger a draft that already exists?) rather than a side effect of
this feature. Recorded as a known boundary (§8), not a gap that was missed.

## 3. Recorded decisions (quick-reference)

| Question | Decision |
|---|---|
| New app or extend `performance`? | Extend — both features are fundamentally *about* `PerformanceAgreement` |
| Calibration cohort unit | Department (`CalibrationSession.department`, nullable = org-wide) — reuses the rating-distribution dashboard's own grouping |
| Who convenes/records calibration | hr_admin only, recording an offline outcome — not a live multi-party tool |
| Calibration eligibility | Only `FINAL_SIGNED`/`ARCHIVED` agreements |
| Does an adjustment overwrite silently? | No — `CalibrationAdjustment` (immutable, reason required even for "no change") + `PerformanceAgreement.history` (existing `simple_history`) + `log_access`, three independent trails |
| Does an adjustment trigger re-signature? | **No** — it's an HR/committee consistency act, not a renegotiation between employee and Head; `AgreementSignature`/`AgreementDocument` for the original sign-off are untouched and remain the historical record |
| Calibration session read access | hr_admin/auditor only (cohort-wide); the agreement's own audience sees their own row via the agreement, same as `return_reason` |
| 360 attaches to which system | New models next to `PerformanceAgreement`, NOT the legacy `Feedback` model |
| 360 rating structure | Fixed 3-criterion 1–5 scale (matches `InterviewScorecard`) + `strengths`/`development_areas` free text |
| Who can be a rater | `self`/`manager` automatic; `peer`/`direct_report` nominated (by subject or Head/hr_admin) + Head/hr_admin-approved |
| Visibility to Head/hr_admin/auditor | Full, attributed, always |
| Visibility to the subject — manager | Full, attributed (no new exposure vs. existing `final_head_comment`) |
| Visibility to the subject — peer/direct-report | Ratings only, pooled per relationship type, ≥3 responses in that bucket, **never free text** |
| Does 360 feed `final_score`? | No — qualitative context only |
| Blind-review-style rater sequencing? | No — the anchoring risk it protects against doesn't exist here |
| `CompProposal` linkage | Confirmed unbuilt; explicitly out of scope this session |

## 4. Data model

### 4.1 `performance.CalibrationSession`

`period` (FK, PROTECT), `department` (FK, nullable — blank = org-wide), `status` (open/completed),
`meeting_date`, `participants_note` (free text — who attended), `summary` (free text — overall committee notes,
e.g. "distribution reviewed, no changes needed"), `convened_by`, `completed_at`.

### 4.2 `performance.CalibrationAdjustment`

`session` (FK, CASCADE), `agreement` (FK, PROTECT — never orphan an audit row), `previous_score` (captured at write
time), `new_score` (nullable = no change), `reason` (required), `adjusted_by`, `created_at`. One row per
(session, agreement) — a unique constraint. No update/delete route; a correction is a new session or a documented
follow-up row, matching `AgreementSignature`'s own "no update/delete path exists" precedent.

### 4.3 `performance.Feedback360Request`

`agreement` (FK, CASCADE), `status` (open/closed), `opened_by`, `due_date`, `closed_at`. Creation gated to
`agreement.status in PerformanceAgreement.CONTRACTED_STATUSES` (AGREED or later — KPIs must already be agreed
before "how do you work with this person" input is meaningful). Closing is permissive (report, don't block — same
philosophy as `archive_period`): outstanding raters are just left `PENDING_APPROVAL`/unresponded, not blocking.

### 4.4 `performance.Feedback360Rater`

`request` (FK, CASCADE), `rater` (FK, Employee), `relationship` (self/manager/peer/direct_report — server-derived),
`status` (pending_approval/approved/declined_nomination/withdrawn — "submitted" is derived from whether a
`Feedback360Response` exists, not stored, per the codebase's derive-don't-store philosophy), `nominated_by`,
`approved_by`, `approved_at`. Unique on (request, rater).

### 4.5 `performance.Feedback360Response`

`rater_slot` (OneToOne, CASCADE), `collaboration_rating`/`communication_rating`/`reliability_rating` (1–5),
`strengths`, `development_areas` (both free text), `submitted_at`. Only the named rater may create/edit their own
(force-set server-side, no proxy-entry — same as `InterviewScorecard`), and only while `request.status == open`.

## 5. Access control

### 5.1 `CalibrationSession`/`CalibrationAdjustment`

Write: hr_admin only. Read (list/detail of a session and its adjustments): hr_admin/auditor only. A
`CalibrationAdjustment` also appears embedded on `PerformanceAgreementSerializer` (`calibration_adjustments`,
read-only) so the agreement's existing audience (self, Head/delegate, hr_admin, auditor —
`PerformanceAgreementPermission`) sees it without a second permission surface.

### 5.2 `Feedback360Request`/`Feedback360Rater`

Read: same audience as the parent agreement (`PerformanceAgreementPermission`, nested under
`performance-agreements/{id}/`). Open/close: Head/hr_admin. Nominate: subject, Head, or hr_admin (nomination
authority — see §2.9). Approve/decline a nomination: Head/hr_admin only.

### 5.3 `Feedback360Response`

Create/update: the named `rater` only, force-set server-side, while their slot is `approved` and the request is
`open`. Read: gated per §2.10 — full detail unconditionally to the Head/hr_admin/auditor and to the rater's own
row; the subject's view is masked in `to_representation` exactly like `InterviewScorecardSerializer` already masks
blind-review scorecards, except the mask here is permanent for peer/direct-report rows (never unlocks) and
replaced with a computed aggregate rather than simply hidden.

## 6. Testing

`performance/test_calibration.py` and `performance/test_feedback360.py`, mirroring `test_agreements.py`'s and
`test_pc3.py`'s style: service-layer state-machine tests (eligibility gating, the immutable-adjustment constraint,
score/hr_attention recomputation, history capture), permission tests (hr_admin-only session read, nomination
approval authority, no-proxy-entry on responses), and the visibility/aggregation tests (the 3-response floor, free
text withheld from the subject for peer/direct-report rows, full attribution to the Head). e2e coverage adds a
calibration + 360 spec exercising both flows through real logins.

## 7. Frontend

- `/calibration` (hr_admin only, nav: Performance & Growth → "Calibration"): pick a period + department, see the
  eligible cohort (FINAL_SIGNED/ARCHIVED agreements) and the existing rating-distribution matrix for context, open
  a session, record an outcome per agreement (no-change or adjust-with-reason), close the session.
- A `Feedback360Section` embedded on the existing agreement card (`MyPerformancePage`/`TeamPerformancePage`) —
  nominate raters, see nomination/approval status, and (per §2.10) the subject's own self+manager responses in
  full plus the peer/direct-report aggregate once available; the Head's view shows every response attributed.
- `/my-feedback-requests` (roles: `[]`, like `/my-interviews` — being nominated as a rater isn't tied to a role):
  the list of 360 rounds this person has been approved to rate, with a submit/edit form.

## 8. Known boundaries

- No live multi-party calibration meeting tooling — hr_admin records an offline outcome (§2.3), by design.
- No `CompProposal` linkage — confirmed unbuilt, deliberately out of scope this session (§2.13).
- No re-signature on a calibration adjustment (§2.4) — revisit if a future legal/CCMA review demands it; the
  service-layer change would be small, the audit trail already produced would not need to change.
- Peer/direct-report free text never reaches the subject, ever, even in aggregate/paraphrased form (§2.10) — a
  deliberate, not merely a not-yet-built, limitation.
- Direct-report feedback may permanently sit below the 3-response floor in a small team and never surface to the
  subject even as an aggregate (§2.10) — accepted cost of protecting the group most likely to fear retaliation.
- No automatic re-open of a `Feedback360Request` when an agreement is later amended (`amend_agreement`) — a 360
  round tied to a pre-amendment revision is left as-is; a fresh round can be opened by hand if wanted.
- `missing_calibration_handler` (§2.12) flags a period-wide gap per-employee (the registry's only shape) — it does
  not distinguish "nobody has looked at this yet" from "hr_admin decided this department needs no calibration this
  year," since the latter still requires opening a session (even one with zero adjustments) to be recorded at all.
