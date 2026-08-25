# Recruitment: Interview Scheduling, Panel Scorecards, Background Checks, External Careers Portal — Design Spec

C6 (`ROADMAP-2026-08.md` §7.3 #19; `NEXT_AGENT_BRIEF.md`: *"pipeline stages exist but the interview step is a
bare stage change; no external-applicant self-application."*). The product owner, asked whether to scope this
down, chose **"everything in one pass"**: interview scheduling, panel scorecards, background/reference-check
tracking, and the external careers portal, built together. Third C6 sub-item shipped this cycle, after
mandatory-training compliance and succession/talent pools.

`docs/MVP-Backlog.md` A3 #9/#10 bound the shape: background checks are **tracking, not vendor integration**
("SA vetting is often manual/legal rather than API-shaped — low leverage"), and the careers portal is the
**internal-first, self-hosted application form**, not a job-board integration (PNet/Career24/LinkedIn stays
parked).

---

## 1. Structural decision: all four land in the existing `recruitment` app

Considered a new app (the `succession` precedent: a new app when the feature is "a single talent-management
concern that needs to read a kernel app but that nothing else needs a reverse dependency on"). Rejected here —
the opposite is true for all four pieces:

- Interview sessions, scorecards, and background checks are **direct extensions of `Applicant`**, the pipeline
  object `recruitment` already owns. They have no existence independent of an `Applicant` row, are read/written
  by exactly the same audience (`recruiter`/`hr_admin`, via the same `IsRecruiterOrHRAdmin` shape most of
  `recruitment` already uses) plus a narrow row-level carve-out (assigned interviewers), and nothing outside
  `recruitment` needs a reverse dependency on them — same "no reverse dependency needed" test the succession
  spec used, but here it points at *not* splitting, because the forward dependency (these new models importing
  `Applicant`/`Requisition`) is already inside the app boundary that owns those models.
- The careers portal doesn't create a new domain object at all — it's a new **entry point** (public,
  unauthenticated) into the exact same `Applicant`/`ConsentRecord` machinery `recruitment` already has, plus two
  new fields on existing models (`Requisition.external_posting`/`description`, `Applicant.source`/`resume`).
  Putting the public views in a new app would mean that app importing `recruitment.Applicant` directly anyway
  (a real FK is unavoidable — the whole point is "creates a real `Applicant` row"), which only recreates the
  peer-import problem a new app is supposed to avoid.

New files inside `recruitment/`: `careers.py` (public serializers, views, URL list — kept in one file
deliberately, so the entire anonymous-write surface is auditable by reading one module, not scattered across
`views.py`/`serializers.py` alongside everything else), `validation.py` (resume content-sniffing), plus
additions to `models.py`, `serializers.py`, `views.py`, `permissions.py`, `services.py`, `urls.py`.

---

## 2. Structural decisions, A–D

### 2.1 Interview scheduling — `InterviewSession`

```
InterviewSession(TimestampedModel)
    applicant         FK Applicant, CASCADE, related_name="interview_sessions"
    round_number       PositiveSmallIntegerField, default=1 — cheap multi-round support: several
                        InterviewSession rows per applicant, ordered by round; no separate "round" object
    scheduled_at        DateTimeField
    duration_minutes    PositiveSmallIntegerField, default=60
    location            CharField(300, blank) — free text: a room name or a video-call URL. No calendar
                        integration (brief: "free text is fine")
    status               CharField, choices SCHEDULED / COMPLETED / CANCELLED, default SCHEDULED
    notes                TextField(blank) — recruiter's own logistics/context notes, distinct from a
                        scorecard's per-interviewer notes
    interviewers         ManyToManyField Employee, related_name="interview_panels" — the panel. Plain M2M,
                        not a through-model: no per-panelist attribute is needed beyond "have they
                        submitted a scorecard yet", which InterviewScorecard already answers via its own
                        (session, interviewer) uniqueness
    created_by            FK Employee, null, SET_NULL, related_name="interview_sessions_created"
    history               HistoricalRecords()
```

Validated in `InterviewSessionSerializer.validate()` (no `services.py` — see §2.4, same reasoning as
succession): `applicant.current_stage` must be `Applicant.Stage.INTERVIEW` (mirrors the brief's own framing —
"tying an Applicant (at INTERVIEW stage) to one or more scheduled sessions") and `interviewers` must be
non-empty. No direct FK to `establishment.Position`: the position context a session might want is already
reachable transitively via `applicant.requisition.positions` — adding a second, redundant link would let the
two disagree with no mechanism keeping them in sync, the same "derive, don't duplicate" reasoning
`Position.current_occupant` already uses for occupancy.

### 2.2 Panel scorecards — `InterviewScorecard`, fixed criteria, blind until self-submitted

```
InterviewScorecard(TimestampedModel)
    session         FK InterviewSession, CASCADE, related_name="scorecards"
    interviewer      FK Employee, CASCADE, related_name="interview_scorecards"
    skill_rating      PositiveSmallIntegerField, choices 1-5
    communication_rating   PositiveSmallIntegerField, choices 1-5
    culture_fit_rating     PositiveSmallIntegerField, choices 1-5
    comments          TextField(blank)
    recommendation     CharField, choices STRONG_HIRE / HIRE / NO_HIRE / STRONG_NO_HIRE
    history            HistoricalRecords()
    constraint: UniqueConstraint(session, interviewer) — one scorecard per interviewer per session
```

**Fixed criteria, not per-requisition configurable.** The brief left this open ("configurable-ish per
requisition or fixed criteria, your call"). A configurable-criteria system needs a new model (criteria
definitions, per-requisition assignment, per-scorecard dynamic score rows keyed to criteria instead of fixed
columns) for a benefit the brief itself frames as optional ("keep this configurable-ish... your call, don't
over-engineer if it adds a lot of complexity for marginal benefit"). Three fixed criteria — role-relevant
skill, communication, culture fit — is standard interview-panel practice and covers the general case; recorded
as a known boundary (§8), not a gap.

**Rating scale: 1-5**, matching `performance`'s own vocabulary (`performance/models/agreements.py`:
`RATING_MIN, RATING_MAX = 1, 5`; `performance/models/cycles.py`: `RATING_CHOICES = [(i, str(i)) for i in
range(1, 6)]`) — brief's own suggestion to stay consistent, so a rater moving between a performance review and
an interview scorecard isn't relearning a second scale. Defined locally in `recruitment/models.py` (a plain
tuple), not imported from `performance` — `performance` is an ordinary domain app, not kernel, and this is a
constant, not a query, so there's no seam to import through; duplicating a five-element tuple is cheaper than
inventing a shared-constants module for one reused literal.

**Blind review (anti-anchoring) — decided, not defaulted.** A real hiring-practice concern: if Interviewer B
can see Interviewer A's "strong hire" before submitting their own scorecard, B's score anchors on A's instead of
being independent. Decision: `InterviewScorecardSerializer.to_representation` hides the rating/comments/
recommendation fields of another interviewer's scorecard **until the viewer has submitted their own scorecard
for that same session** — at which point every scorecard for the session becomes visible to every panelist
on it (peer scores unlock together, once you've committed your own; this is the standard blind-review pattern,
not a permanent embargo). `recruiter`/`hr_admin` always see full detail immediately — they're not being asked
to form an independent first impression, they're aggregating panel input for a stage-advance decision, which
is the whole point of the field being visible to them at all. Implementation is a single extra query per row
(`InterviewScorecard.objects.filter(session_id=…, interviewer=viewer).exists()`) — negligible at the realistic
scale (a handful of interviewers per session), the same "not the 153-row list-page shape" reasoning succession's
queries seams used (§2.7 there).

Considered and rejected: locking a scorecard from edits once submitted (to stop an interviewer revising their
score after seeing a peer's). Not built — your own score can't un-anchor from a peer's after the fact just by
becoming uneditable, and the blind-review gate already prevents seeing peers' scores until after your own
exists, so an edit-lock adds friction (fixing a genuine typo needs HR intervention) without closing a real gap.
Recorded as a known boundary (§8).

Write: only the interviewer named on a scorecard may create/update it — not even `hr_admin` may author or edit
a scorecard on another interviewer's behalf (no proxy-entry). A real limitation (relayed verbal feedback has
nowhere to go except a session's free-text `notes` field) accepted for this slice, matching succession's own
"a real limitation... accepted for this slice" posture for its single-actor nomination flow.

### 2.3 Background / reference checks — `BackgroundCheck`, tracking only

```
BackgroundCheck(TimestampedModel)
    applicant        FK Applicant, CASCADE, related_name="background_checks"
    check_type        CharField, choices REFERENCE / CRIMINAL_RECORD / QUALIFICATION_VERIFICATION /
                     CREDIT_CHECK / OTHER
    status             CharField, choices NOT_STARTED / REQUESTED / IN_PROGRESS / CLEARED / FLAGGED,
                     default NOT_STARTED
    requested_by        FK Employee, null, SET_NULL, related_name="background_checks_requested"
    requested_at         DateTimeField, null, blank
    completed_at          DateTimeField, null, blank
    notes                  TextField(blank) — outcome/context; can legitimately hold criminal-record or
                        credit-check detail, hence the access decision below
    history                 HistoricalRecords()
```

No `ALLOWED_TRANSITIONS` state machine (unlike `Applicant.Stage`): a real vetting process can legitimately move
non-monotonically (a `flagged` result revised to `cleared` after a documented review, e.g. a false-positive
name match) — free-form status, validated only for a legal enum value.

**Access: `recruiter` + `hr_admin` only, no additional row-scoping.** This reuses `IsRecruiterOrHRAdmin`
directly — the *same* permission class every other `recruitment` endpoint already uses, not a narrower one,
because that class's audience already IS the correct audience here (row_scope=all, and nothing in
`RBAC-Roles.md` names a narrower background-check-specific role). Deliberately **not** registered in
`rbac_audit/tiers.py`'s `FIELD_TIERS` (no per-field tiering): the whole model is Sensitive by nature (brief:
"this is Sensitive-tier data by nature (criminal/credit checks especially)"), not a subset of its fields the
way `Applicant`'s demographics are a subset of `Applicant`'s otherwise-public fields — matching the documented
exception `rbac_audit/tiers.py` already carries for `performance.Review`/`Feedback` and this session's own
`succession.SuccessionCandidate`: "gated by whole-endpoint role/row checks instead," used when the model itself
is what's sensitive, not a field within it, and the coarse permission class already excludes everyone else.
Interviewers (who get row-level access to their own `InterviewSession`s, §2.1) get **no** access to
`BackgroundCheck` at all — a real vetting outcome is exactly the kind of thing an interviewer forming their own
independent impression should not see (compounding the blind-review reasoning in §2.2: a "flagged" criminal
check would anchor a panelist's score far harder than a peer's rating would).

### 2.4 No `services.py` for A–C

Same reasoning succession's spec §2.4 already recorded for a structurally identical situation: every write here
is single-row (schedule a session, submit a scorecard, log a background-check status change) with validation
that fits comfortably in each serializer's own `validate()`. The one exception is the careers portal (§2.5,
§4) — that genuinely is a multi-step write (validate → create `Applicant` → conditionally record consent →
conditionally set demographic fields, atomically), so it gets a real service function,
`recruitment/services.py::submit_portal_application`, wrapped in `transaction.atomic`.

### 2.5 Careers portal — new fields, not a new applicant model

```
Requisition gains:
    description         TextField(blank) — the free-text job description the model didn't have; also useful
                        internally (RequisitionSerializer already exposes it) even for postings that never
                        go external
    external_posting      BooleanField, default=False — HR opts a requisition INTO public visibility;
                        default False so the existing ~dozen seeded/demo requisitions don't silently become
                        public the moment this ships

Applicant gains:
    source                CharField, choices INTERNAL / PORTAL, default=INTERNAL — provenance only, never
                        read by the stage machine, retention handler, or hire flow, which is the point: a
                        portal-sourced row is byte-for-byte the same kind of row an internal one is
    resume                FileField(upload_to="applicant_resumes/%Y/%m/", null, blank) — general, not
                        portal-only: an internally-created applicant can also have a CV attached via a
                        recruiter PATCH, so nothing downstream needs a source check to decide whether a CV
                        might exist
    resume_content_type     CharField(120, blank) — server-sniffed (§4.3), never client-trusted, same
                        pattern as `documents.EmployeeDocument.content_type`
    resume_size_bytes         PositiveIntegerField, default=0
```

**Why this and not a separate `PublicApplication` staging model that gets promoted to `Applicant` on review.**
Considered — some ATS designs keep public submissions in a quarantine table until a human confirms them, to
keep unvetted public input further from the real pipeline. Rejected: the brief is explicit that a portal
applicant must be "the SAME `Applicant` model, same pipeline, same stage machine, same retention/anonymisation-
on-rejection behaviour, so nothing downstream needs to know whether an applicant came from HR-entered data or
self-application." A staging table would violate that directly — every downstream consumer (retention, the
recruitment dashboard, the hire flow) would need to learn about a second applicant shape, or a promotion step
would need to exist and be a second, parallel "is this really final" decision point the brief didn't ask for.
The real containment the staging-table idea is chasing (spam/bad input never reaching the real pipeline) is
handled instead by validation-at-the-door: throttling (§3.3), content-sniffed upload validation (§4.3), and the
honeypot (§3.3) reject bad submissions before a row is ever created, rather than after.

---

## 3. Access control

### 3.1 `InterviewSession`

| Action | Who |
|---|---|
| Create / update / list-all / delete | `recruiter`, `hr_admin` (`IsRecruiterOrHRAdmin`, unchanged shape) |
| Read own assigned sessions | Any employee named in `interviewers` for that specific row — a **row-level**, not role-level, grant: "assigned interviewer" isn't a `RBAC-Roles.md` role, it's an ad-hoc M2M membership any employee (a line manager, a senior engineer asked to sit on a panel, even another recruiter) can hold for one session and not another |

New permission class `IsRecruiterOrHRAdminOrAssignedInterviewer` (`recruitment/permissions.py`): `has_permission`
requires only an authenticated employee (list/create still narrowed by role inside the view — see below);
`has_object_permission` grants recruiter/hr_admin everything, and grants a plain assigned interviewer
**SAFE_METHODS only** on rows where they're listed in `interviewers`. `InterviewSessionViewSet.get_queryset`
does the row-filtering for `list`: recruiter/hr_admin see everything; everyone else sees only sessions where
they're an interviewer (never an empty-vs-403 ambiguity — a non-interviewer, non-recruiter employee gets a
genuinely empty list, matching the shape `ChecklistInstance`'s reporting-chain filter already uses elsewhere in
this codebase, not a 403 on the list endpoint itself).

**What an interviewer sees of the applicant.** Not the full `ApplicantSerializer` (which exposes Sensitive-tier
demographics to anyone who can reach it, gated only by `IsRecruiterOrHRAdmin` at the whole-endpoint level — an
assigned interviewer is explicitly *not* that audience). `InterviewSessionSerializer` instead nests a
deliberately narrow, **always-the-same-shape-regardless-of-viewer** `applicant_summary`: `id`, `first_name`,
`last_name`, `requisition` (id + title), `current_stage`, `resume` (a download URL, if present). No
`race`/`gender`/`disability_status`, no `email`/`phone`/`date_of_birth`, no `rejected_reason`. This is
deliberately uniform for every caller, including recruiter/hr_admin — they already have `/applicants/{id}/` for
the full picture, so there's no benefit to conditionally widening this endpoint's payload for them, and keeping
it single-shape means there is no per-role branch in this serializer that a future edit could get wrong and
accidentally leak Sensitive-tier fields to an interviewer. "Prior-stage notes" (the brief's suggested inclusion)
was considered and left out of this summary specifically: `ApplicantStageEvent.notes` can contain recruiter
commentary written for an HR audience (e.g. screening impressions, offer-negotiation context) that wasn't
written with an ad-hoc interviewer-audience in mind — surfacing it by default risked leaking exactly the kind
of pre-interview anchoring the blind-review design in §2.2 is trying to prevent from a different angle. Left
as a known boundary (§8), not built.

### 3.2 `InterviewScorecard`

| Action | Who |
|---|---|
| Create | The named `interviewer` only, and only for a session they're assigned to — `interviewer` is force-set to the requesting employee server-side, never client-supplied, so nobody can submit "on behalf of" someone else |
| Update (own scorecard) | Same interviewer only |
| Read | `recruiter`/`hr_admin` (full, always); any interviewer on the session (own scorecard always; peers' scorecards only after their own is submitted — §2.2) |

`InterviewScorecardViewSet.get_queryset`: recruiter/hr_admin get everything; anyone else gets scorecards for
sessions where they're a listed interviewer (their own row plus — subject to the `to_representation` masking
above — their peers'). A plain employee with no relationship to the session at all gets neither role access nor
row access and sees nothing.

### 3.3 `BackgroundCheck`

`recruiter`/`hr_admin` only, full CRUD, via the existing `IsRecruiterOrHRAdmin` (§2.3) — no interviewer access
at all.

### 3.4 Careers portal — public surface

| Endpoint | Auth | Throttle |
|---|---|---|
| `GET /api/v1/careers/postings/`, `GET /api/v1/careers/postings/{id}/` | `AllowAny` | `careers_read` (per-IP, generous — defends against scraping/DoS, not a real abuse vector on its own) |
| `POST /api/v1/careers/apply/` | `AllowAny` | `careers_application_burst` + `_sustained` (per-IP) + `_email` (per submitted email) |

**CSRF.** No special handling needed — verified against `login_view`'s own shape, the only other
anonymous-plus-POST endpoint in the system. DRF's `SessionAuthentication.enforce_csrf` only runs once a request
has actually authenticated a user via a session cookie; an anonymous request with no valid session never
reaches that check (and `APIView.as_view()` already exempts DRF views from Django's own `CsrfViewMiddleware`,
which is what lets `login_view` itself work with no session yet). A careers-portal POST from a browser with no
prior session is in exactly the same position — no CSRF token required, none issued.

**Anti-abuse, concretely:**
1. **Throttling** — three new `AnonRateThrottle`/`SimpleRateThrottle` subclasses in `rbac_audit/throttling.py`
   (same file as `LOGIN_THROTTLES`, same reasoning: this is the second-ever anonymous-write surface in the
   system, after login, and deserves the same category of defence): `CareersApplicationBurstThrottle` (per-IP,
   `5/min`), `CareersApplicationSustainedThrottle` (per-IP, `20/day`), `CareersApplicationEmailThrottle` (keyed
   on the submitted email, lower-cased, `SimpleRateThrottle` subclass mirroring `LoginUsernameThrottle`
   exactly, `3/hour`) — the email-keyed limit is what stops a distributed-IP attacker hammering one specific
   email address's ability to apply (or spamming one requisition with junk from many source IPs but a handful
   of reused emails), the same asymmetry `login_username` closes against distributed credential-stuffing.
   `CareersReadThrottle` (`60/min`, per-IP) on the read-only postings list/detail.
2. **Upload validation** — `recruitment/validation.py` (§4.3): content-sniffed (PDF/DOCX/JPEG/PNG magic bytes),
   never filename/extension-trusted, 5MB cap (tighter than `documents`'s 10MB — a CV is normally a small text
   document, unlike a scanned ID or contract).
3. **Honeypot** — a hidden `website` field on the public form (never rendered visibly, so a human never fills
   it; a scripted bot filling every field blindly does). If non-blank, the view returns an ordinary 201
   success **without creating any row** — indistinguishable from a real success to a bot, so it doesn't learn to
   adapt. Cheap (a few lines), so built despite the brief only asking it be "considered."
4. **Duplicate-application handling** — the existing `one_application_per_email_per_requisition`
   `UniqueConstraint` is unchanged; `submit_portal_application` attempts the create and catches `IntegrityError`
   (not a pre-`.exists()` check, which would race under concurrent submission) and re-raises as a plain
   `ValueError`, which the view turns into a 400 with a human-readable message — never a 500.
5. **Consent gates storage, not submission.** If `demographic_consent` isn't sent as true, any
   race/gender/disability values in the payload are **silently ignored** (all three fields stay at their model
   default, `not_disclosed`) rather than the whole application being rejected. Rejecting a genuine applicant's
   entire submission over an unchecked consent box would be a worse outcome than just not persisting the
   demographic answer they gave without consent — and it would create an incentive to tick the box just to get
   the application through, which is the opposite of what informed consent is supposed to protect. This mirrors
   the internal flow's own posture (`ApplicantSerializer.validate`: consent gates whether demographic *fields
   can be written*, not whether the applicant record can exist at all) rather than inventing a new rule for the
   public path.

---

## 4. Data model detail

### 4.1 Migration

One migration on `recruitment`: `Requisition.description`/`external_posting`, `Applicant.source`/`resume`/
`resume_content_type`/`resume_size_bytes`, plus the three new models (`InterviewSession`, `InterviewScorecard`,
`BackgroundCheck`) and their `simple_history` shadow tables.

### 4.2 `InterviewSession`/`InterviewScorecard`/`BackgroundCheck`

See §2.1–2.3 for full field lists.

### 4.3 `recruitment/validation.py` — resume content-sniffing

Duplicates `documents/validation.py`'s magic-byte sniffing (PDF `%PDF-`, JPEG `\xff\xd8\xff`, PNG the 8-byte
PNG signature, DOCX via the `word/document.xml` zip-member check) rather than importing it. Not optional here —
`recruitment` may not import `documents` directly (`hcm/README.md` module rule #1: peer apps only through a
`queries.py` seam, and `documents/validation.py` is a plain utility function, not a query — there is no seam
that fits it). This mirrors an **existing** precedent in this exact codebase: `documents/validation.py`'s own
docstring already duplicates `policies/extraction.py`'s zip-sniffing rather than importing it, for the same
peer-boundary reason. A future third consumer would be the trigger to promote this into a genuinely shared
kernel utility (e.g. `rbac_audit`); two independent duplicates is the same number this codebase already
tolerates today, not a new kind of debt. Cap: `MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024`.

### 4.4 `recruitment/services.py::submit_portal_application`

```
@transaction.atomic
def submit_portal_application(*, requisition, first_name, last_name, email, phone, date_of_birth, resume,
                               race="", gender="", disability_status="", demographic_consent=False) -> Applicant
```
Raises `ValueError` (→ 400) for: requisition not `OPEN`/not `external_posting`; resume fails content-sniffing
or exceeds the size cap; duplicate email for this requisition (via `IntegrityError` catch, §3.3.4). On success:
creates the `Applicant` (`source=PORTAL`), and — only if `demographic_consent` is true — records a
`ConsentRecord` (`purpose=DEMOGRAPHIC_SELF_ID`, `actor=None`: there is no employee actor for a public
submission, and `record_consent` already supports that) and then sets whichever of race/gender/disability_status
were actually supplied.

---

## 5. Frontend

### 5.1 Authenticated surfaces

- **`ApplicantDetailPage.tsx`** gains two new sections, alongside the existing Offer/Assessments sections:
  - **Interviews** — list of `InterviewSession`s for this applicant (round, when, location, panel, status),
    a "Schedule interview" form (recruiter/hr_admin only — role-gated client-side, enforced server-side by
    `IsRecruiterOrHRAdminOrAssignedInterviewer`/`get_queryset` regardless), and each session expands to show its
    scorecards in aggregate (average per criterion, recommendation counts, and each interviewer's individual
    card) — visible here because `ApplicantDetailPage` is itself recruiter/hr_admin-only territory
    (`RequireRole roles={['recruiter', 'hr_admin']}` in `App.tsx`, unchanged), so the blind-review masking
    doesn't even apply to this view (§2.2 — recruiter/hr_admin always get full detail).
  - **Background checks** — list + "Log a check" form (recruiter/hr_admin only).
- **New page `MyInterviewsPage.tsx`**, route `/my-interviews`, **`roles: []`** in `navConfig.ts` (every
  authenticated employee — being tapped as a panelist is an ad-hoc assignment, not tied to any role) — lists
  the current employee's own assigned sessions (via `GET /interview-sessions/` under their own row-scoped
  queryset) with the narrow `applicant_summary`, and a scorecard submission form per session once its status
  allows it. This is the surface that satisfies "the assigned interviewers need at least read access to their
  own assigned sessions and applicant summary" for someone who holds no recruitment-module role at all.

### 5.2 Public surfaces — genuinely unauthenticated routes

`App.tsx`'s entire route tree currently sits under one `<Route element={<RequireAuth />}>` wrapper — there was
no precedent for a route the SPA renders without a session. Two new top-level `<Route>`s, siblings of
`/login`, **outside** `RequireAuth`:

- `/careers` → `CareersListPage.tsx` — public list of open, externally-posted requisitions.
- `/careers/:id` → `CareersPostingPage.tsx` — one posting's detail plus the public application form (name,
  email, phone, date of birth, optional race/gender/disability_status with a "prefer not to say" default and an
  explicit consent checkbox framed the same way the internal consent-capture flow is, resume upload, and the
  invisible honeypot field).

Both use a minimal standalone layout (no `AppShell`/sidebar/nav — an anonymous visitor has no session-driven
nav to show) and the **existing** `api` client unchanged: `api`'s CSRF/credentials handling
(`credentials: 'same-origin'`, `ensureCsrfCookie()` before mutating calls) works identically for an anonymous
caller (§3.4 established no CSRF token is actually required here, but sending the cookie is harmless), and
`AuthProvider`'s unauthenticated-response handling only fires on a 401, or a 403 outside
`UNAUTHORIZED_EXEMPT` — the public careers endpoints never return either for a legitimate anonymous request
(they're `AllowAny`), so mounting `AuthProvider` around these routes too (it already wraps the whole `<Routes>`
tree) is inert, not a hazard.

---

## 6. Testing

Mirrors `recruitment/test_api.py`'s existing shape, extended:
- `InterviewSession`: applicant must be at `INTERVIEW` stage to schedule; recruiter/hr_admin CRUD; a plain
  employee with no panel membership sees an empty list and 403/404s a direct retrieve; an assigned interviewer
  sees their own session (read-only) and not others'.
- `InterviewScorecard`: one scorecard per (session, interviewer) enforced; only the named interviewer may
  create/update their own; blind-review masking — Interviewer B cannot see Interviewer A's rating/comments/
  recommendation before B has their own row, and can immediately after; recruiter/hr_admin always see full
  detail; a non-panel employee gets nothing.
- `BackgroundCheck`: recruiter/hr_admin CRUD; every other role (including an assigned interviewer) 403.
- Careers portal: postings list only returns `OPEN` + `external_posting=True` rows; a closed or
  non-externally-posted requisition 404s a direct apply attempt; a valid submission creates a real `Applicant`
  (`source=portal`) that then flows through the ordinary stage machine and retention/anonymisation path
  unchanged; a duplicate email for the same requisition 400s, not 500s; an unrecognised/oversized resume 400s;
  the honeypot field silently no-ops (201, no row created); demographic fields are dropped when
  `demographic_consent` is false and persisted (plus a `ConsentRecord`) when true; the three new throttle scopes
  actually throttle (burst, sustained, per-email) — same assertion shape `rbac_audit`'s existing login-throttle
  tests already use.
- e2e (`careers-portal.spec.ts` and an interview-scoring addition to the existing recruitment flow): an hr_admin
  flags a requisition externally-postable; an anonymous browser context (no login) applies through `/careers`;
  hr_admin sees the portal-sourced applicant in the normal pipeline, advances them to `interview`, schedules a
  session with two interviewer logins; each interviewer logs in, sees the session on `/my-interviews`, submits a
  scorecard, and cannot see the other's until their own is in; hr_admin sees both in aggregate and advances the
  applicant to hire.

---

## 7. Recorded decisions (quick-reference)

1. All four sub-parts land in the existing `recruitment` app — direct extensions of `Applicant`/`Requisition`,
   not a new domain (§1).
2. `InterviewSession`: plain M2M `interviewers` (no through-model), multi-round via `round_number`, no direct
   `Position` FK (reachable transitively via `applicant.requisition.positions`) (§2.1).
3. Fixed three-criteria scorecard (skill/communication/culture fit), 1-5 scale matching `performance`'s own
   vocabulary — not a configurable-per-requisition criteria system (§2.2).
4. **Blind review: peer scorecards stay hidden from an interviewer until they've submitted their own** for that
   session; recruiter/hr_admin always see full detail immediately (§2.2, §3.2).
5. No proxy-entry — only the named interviewer may author/edit their own scorecard, not even hr_admin (§2.2).
6. `BackgroundCheck` is tracking-only (no vendor integration, per `docs/MVP-Backlog.md` A3 #9), gated by the
   existing `IsRecruiterOrHRAdmin` with no interviewer access at all and no per-field tiering — the whole model
   is sensitive, matching the documented `performance.Review`/`succession.SuccessionCandidate` exception
   pattern (§2.3).
7. Careers portal reuses the real `Applicant` model (`source`/`resume` fields added), not a staging/quarantine
   table — containment against bad public input is at the validation/throttling layer, not a second pipeline
   shape downstream consumers would need to learn about (§2.5).
8. An interviewer's applicant view is a fixed, narrow `applicant_summary` (name, requisition, stage, resume) —
   **no** demographics, **no** stage-event notes, uniform for every caller including recruiter/hr_admin (§3.1).
9. Public careers endpoints: `AllowAny` + three new throttle scopes in `rbac_audit/throttling.py` (burst,
   sustained, per-email) mirroring `LOGIN_THROTTLES`'s shape exactly; no CSRF token needed, verified against
   `login_view`'s identical anonymous-POST shape (§3.4).
10. Resume upload validation duplicates `documents/validation.py`'s content-sniffing rather than importing it
    (peer-app boundary; matches that file's own precedent for the same reason) (§4.3).
11. Consent gates **storage** of demographic answers, not **submission** of the application — an unconsented
    demographic value is silently dropped, not treated as a submission-blocking error (§3.4.5).
12. Honeypot field on the public form; a filled honeypot returns an ordinary success with no row created (§3.4.3).

---

## 8. Known boundaries

- No configurable per-requisition scorecard criteria (§2.2) — fixed three-criterion vocabulary only.
- No scorecard edit-lock after submission (§2.2) — blind review already prevents anchoring on a peer's score;
  an edit-lock would only add friction for a typo fix.
- No proxy scorecard entry by hr_admin on an interviewer's behalf (§2.2) — a real limitation for relayed verbal
  feedback, which has nowhere to go except a session's own free-text `notes`.
- An interviewer's applicant summary excludes prior stage-event notes (§3.1) — those can carry HR-audience
  commentary not vetted for an ad-hoc interviewer audience; a narrower, curated "interview brief" note field
  would be a reasonable future addition, not built here.
- No calendar/video-conferencing integration (§2.1) — `location` is free text, per the brief.
- No staging/quarantine table for public submissions before they enter the real pipeline (§2.5) — deliberate;
  containment is at the validation/throttling layer instead.
- Careers portal has no applicant-facing "track your application status" view — a real, common ATS feature,
  out of scope for this pass (the brief's minimum is list + apply, not a full self-service portal).
- No CAPTCHA on the public form — throttling + content-sniffing + honeypot were judged sufficient for this
  scale; a CAPTCHA is a cheap future addition if abuse is actually observed in production.
