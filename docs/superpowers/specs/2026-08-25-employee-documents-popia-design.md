# Employee Documents & POPIA Rights — Design Spec

C2 (`docs/sprints/backlog-uat1-and-c2-c7.md`; `docs/MVP-Backlog.md` Part B item 2; `NEXT_AGENT_BRIEF.md` §7.1 #9,
§7.2 #13-14). Closes the third of the original five demoable-lifecycle breaks — "personal documents (ID,
contract, quals)" — leaving only leave/absence (blocked on a decision, not effort).

---

## 1. The problem

### 1.1 Five things under one backlog item, three of which are known patterns and two of which are not

The C2 checklist bundles:

1. `EmployeeDocument` — tiered, consent-aware, authenticated download. **Known pattern**: `policies.Policy` already
   does versioned document storage + authenticated download; `policies/extraction.py` already fixed the
   extension-trusting defect this needs to avoid repeating.
2. Qualifications feeding WSP/ATR + EE reporting. **Needs investigation** — is there already a qualification model,
   and does anything already feed those reports?
3. Dependants / emergency contacts. **Known pattern** — a small per-employee model with self-service CRUD, same
   shape as `learning.EmployeeSkill`/`Certification`.
4. Data-subject export/erasure request workflow. **New ground.** The consent *plumbing* exists
   (`rbac_audit.ConsentRecord`) but nothing lets an employee ask for their data, and nothing executes an erasure.
5. Retention scopes for documents/evidence. **Known pattern** — `RetentionRule` seeding, same shape as
   `core_hr/migrations/0011_seed_employment_retention_rules.py`.

This spec covers all five, but spends its real design budget on (4), the one item with genuine ambiguity, and
records the investigation findings for (2) before proposing anything.

### 1.2 Investigation: what already feeds WSP/ATR and EE reporting

`learning.Certification` (name, issuing_body, credential_id, issue_date, expiry_date) is the qualification/
credential model — it already exists and is not duplicated by anything else. `learning.TrainingRecord` is the
*training* model, and it alone feeds `learning/views.py::wsp_atr_export` today: the CSV joins `TrainingRecord`
rows to `EmployeeVersion`'s occupational_level/race/gender/disability_status. `Certification` rows are not in that
export at all, and EE reporting's only textual reference to "qualification" is a fixed dropdown label in
`ee_reporting/constants.py::DIFFERENTIAL_REASONS` (EEA4 Section E) — not data-driven from any model.

So "qualifications → WSP/ATR + EE" is a real, narrow gap: the SETA return should include people's *qualifications*
alongside their *training*, and doesn't. Decision (§2.4 below): extend `wsp_atr_export` to union `Certification`
rows into the same CSV with a `record_type` discriminator, joined to the identical demographic fields it already
uses for `TrainingRecord`. That is the entire "EE" linkage too — EE reporting has no separate qualifications
consumer; the demographic join is what "feeds EE" already means for the training rows, and the same join now
covers qualification rows. No new EE-specific code path exists to build.

`EmployeeDocument(type=qualification)` is deliberately **not** hard-linked to `Certification` — see §2.5.

---

## 2. Structural decisions

### 2.1 A new app, `documents` — not folded into `core_hr` or `policies`

`EmployeeDocument` and the POPIA request workflow are per-employee sensitive file storage and a review workflow —
a distinct concern from `core_hr`'s identity/employment-structure data (which is SHARED_KERNEL and imported by
every other app; it should not accrete file-storage and consent-workflow logic) and from `policies`' shape (an
org-wide *broadcast* document with versioning/publishing/acknowledgment — the opposite of a private per-employee
file). One app, one new peer in the `DOMAIN_APPS` list (`rbac_audit/test_module_boundaries.py`), same footing as
`onboarding`.

### 2.2 Dependants / emergency contacts go in `core_hr`, not `documents`

The brief's own suggestion, and the right call: unlike `EmployeeDocument` (file storage + consent + POPIA
workflow — a distinct concern), `Dependant`/`EmergencyContact` are structurally identical to `Employee` itself —
plain per-employee identity-adjacent rows with no file, no consent gate, no workflow. They belong next to
`Employee` in the kernel the same way `EmployeeVersion` does, not in the new app whose whole reason to exist is
file storage and the POPIA review queue.

### 2.3 No new peer-app coupling — `documents` does not import `learning`

`hcm/README.md`'s module rule (mechanically enforced by `rbac_audit/test_module_boundaries.py`): peer apps may
only reach each other through a `<app>/queries.py` seam, never a direct model import, and `establishment` is the
one precedent for a genuine cross-app FK need — it joined `SHARED_KERNEL` because *multiple* apps need a hard
relationship into it. A single optional convenience link from `documents` to `learning.Certification` doesn't
clear that bar. See §2.5 for what this means concretely for the qualification document type.

### 2.4 `wsp_atr_export` gains qualification rows, unioned into the same CSV

`learning/views.py::wsp_atr_export` already lives in `learning`, which already owns `Certification` — no
cross-app import needed for this change at all, it's purely additive within the app that already has the data. A
`record_type` column (`training` / `qualification`) is added; qualification rows carry `name`/`issuing_body` in
the `training_title`/`provider` columns (same shape, different semantic label) and blank `hours`/`cost`/`status`
(concepts that don't apply to a qualification). This directly satisfies the backlog item without inventing an
`EmployeeDocument`-to-`Certification` link.

### 2.5 `EmployeeDocument(type=qualification)` stores the evidence file; it is not the qualification's data record

`learning.Certification` already models the qualification's substance (name, issuing body, credential ID, dates)
and, after §2.4, already feeds WSP/ATR. `EmployeeDocument` exists to store the *evidentiary file* — the scanned
certificate/diploma — as a tiered, consent-aware attachment. The two are related in real-world meaning (the
document evidences the certification) but deliberately **not** modelled as a foreign key between them (§2.3): HR
identifies the link informally via the document's `title` (e.g. "BCom — supporting certificate for the
Certification record dated 2019"), and nothing downstream needs a hard join — the WSP/ATR export reads
`Certification` directly, never `EmployeeDocument`. If a future need for "does this qualification have verifying
evidence on file" arises, it can be answered without a schema change (a `documents/queries.py` seam function
comparing employee IDs + rough title matching), so this is not a closed door, just a deferred one.

### 2.6 Document-type tiers are a row-level property, not per-field `FIELD_TIERS`

`rbac_audit/tiers.py::FIELD_TIERS` maps `model.field → tier`, fine for a fixed schema where every row's
`race` field is equally sensitive. `EmployeeDocument`'s sensitivity varies **by row** (an ID copy and a
qualification certificate are not equally sensitive, but they're the same model and the same `file` field).
`TieredModelSerializer`'s field-dropping doesn't fit that shape, so `EmployeeDocument` uses a `tier` *property*
computed from `document_type` via a `DOCUMENT_TYPE_TIERS` map, and a bespoke permission class does the same job
`can_access_tier_for_target` does for fields — at row granularity — for reads; see §5.

Tier assignments, matched against the closest existing precedent in `FIELD_TIERS`:

| `document_type` | Tier | Precedent |
|---|---|---|
| `id_copy` | Restricted | `Employee.national_id_number` is Restricted; a copy of the document is at least as sensitive |
| `employment_contract` | Restricted | Typically states remuneration — same bar as `compensation.pay_band`/`comp_proposal` (Restricted) |
| `disability_verification` | Sensitive | Matches `EmployeeVersion.disability_detail` (Sensitive) |
| `qualification` | Internal | Matches every `learning.Certification` field (Internal) |
| `other` | Sensitive | Unclassified upload — default to the cautious side, not Internal |

### 2.7 Consent is required for `id_copy` and `disability_verification` only

`identity_verification.BiometricEnrollment` requires active `ConsentRecord.Purpose.BIOMETRIC` consent before
enrolment; that's the precedent for gating a *specific, especially sensitive* category of personal data behind an
explicit consent capture, on top of (not instead of) generic tiering. Rather than gate every document type,
consent is required only for the two categories that most resemble that precedent — direct identity documents and
protected-characteristic evidence:

- **`id_copy`, `disability_verification`** — require an active `ConsentRecord` with a new purpose,
  `Purpose.EMPLOYEE_DOCUMENTS`, before upload succeeds (`DocumentError`, same shape as
  `identity_verification.ConsentRequiredError`).
- **`employment_contract`** — no consent gate. A contract is processed because it *is* the employment
  relationship, not because the employee separately consented to it — consent isn't the right lawful basis for a
  document that constitutes the contract itself, and gating it would be backwards (HR must be able to file a
  signed contract without first extracting a "may we file your contract" consent from the person it's with).
- **`qualification`, `other`** — no consent gate. Internal-tier data (qualification) and unclassified catch-all
  (other) don't fit a fixed consent purpose; access is controlled by tiering alone, same as `Certification` today.

A new `Purpose.EMPLOYEE_DOCUMENTS` choice (rather than reusing `DEMOGRAPHIC_SELF_ID`) is deliberate: it keeps
withdrawal precise. §6.3's erasure path withdraws exactly the consent that covered the erased documents; reusing
`DEMOGRAPHIC_SELF_ID` would also implicate the *profile-level* self-ID answer on `EmployeeVersion`, which erasure
must never touch (§6.1).

### 2.8 Write access to documents/dependants/emergency-contacts is self-or-hr_admin, not generic row-scope

The established pattern for per-employee records (`learning.EmployeeSkill`/`Certification`/`TrainingRecord` via
`RowScopedLearningSerializer`) gates writes with `has_row_access` alone — self, the employee's manager
(`own_team`), or any all-scope role. That's right for skills/training, where a manager plausibly records something
about their report. It is **not** right here: no line manager has a legitimate reason to upload an ID copy,
disability verification document, or another employee's dependant/emergency contact — that is HR administration,
not team management. Writes are narrowed to **self or `hr_admin`** via a new `core_hr.permissions.IsSelfOrHRAdmin`
(same shape as the module-local classes already duplicated in `policies`/`identity_verification`, but placed in
`core_hr` since it's genuinely generic and `core_hr` is the one app every domain app already imports directly —
matching how `learning/views.py` already imports `core_hr.permissions.IsHRAdmin`/`IsHRAdminOrReadOnly` today).

Reads stay broader: `EmployeeDocument` reads go through the row-tier check in §2.6/§5 (so `ee_manager` can read
Sensitive disability-verification docs org-wide, `comp_manager` can read Restricted employment contracts, a
`line_manager` can read Internal qualification docs for their own reports, matching each role's existing generic
tier grants); `Dependant`/`EmergencyContact` reads are deliberately narrower still — self or `hr_admin` only, no
row-scope/tier extension to `line_manager`/`ee_manager`/etc. A manager plausibly needing a report's emergency
contact in a crisis was considered and set aside: the brief frames this as "self-service + an hr_admin view," HR
can always retrieve it operationally, and third-party personal data (§2.9) is exactly the case for the narrowest
reasonable default rather than extending exposure speculatively.

### 2.9 Dependant/EmergencyContact tier: Sensitive by default, not Internal

The employee's *own* equivalent fields (name, DOB) are Public/Sensitive depending on which field. A dependant or
emergency contact is data about **a third party** who is not the one operating any consent or access-control
decision in this system — POPIA's protections apply to them just as much as to the employee, and they have no
seat at the RBAC table. Defaulting to Sensitive (rather than Internal, which is what the *employee's* analogous
contact fields would be) is the more defensible default given that asymmetry; a third-party ID number is
Restricted, matching `Employee.national_id_number`.

---

## 3. Recorded decisions (quick-reference)

1. New app `documents`: `EmployeeDocument`, `DataSubjectRequest`. New models `Dependant`, `EmergencyContact` in
   `core_hr` (§2.1, §2.2).
2. `wsp_atr_export` unions `Certification` rows in; no `EmployeeDocument`↔`Certification` FK (§2.3-2.5).
3. Tier is a row-level property on `EmployeeDocument`, driven by `document_type` (§2.6).
4. Consent (`Purpose.EMPLOYEE_DOCUMENTS`, new) required only for `id_copy`/`disability_verification` (§2.7).
5. Document/dependant/emergency-contact **writes**: self-or-hr_admin only, narrower than generic row-scope (§2.8).
6. Document **reads**: row-tier gated (broad, matches existing per-role tier grants). Dependant/emergency-contact
   reads: self-or-hr_admin only, no broader row-scope extension (§2.8-2.9).
7. Dependant/EmergencyContact default tier: Sensitive (third-party data), Restricted for a third-party ID number.
8. POPIA export/erasure: one workflow, two request types, both **reviewed and actioned by `hr_admin`**, never
   auto-executed (§4).
9. Erasure is an explicit allow-list (documents, dependants, emergency contacts, three named optional `Employee`
   fields) — never a `RetentionRule`-driven blanket delete, and never touches audit logs, employment history, or
   anything under an existing RETAIN rule (§6.1).
10. Retention rules seeded for `documents.EmployeeDocument` (RETAIN while nothing better exists — §7) and
    `core_hr.Dependant`/`core_hr.EmergencyContact` (DELETE, tied to the employee relationship ending, not a fixed
    calendar window — §7).

---

## 4. Data model

### 4.1 `documents.EmployeeDocument`

```
employee            FK core_hr.Employee, CASCADE, related_name="documents"
document_type        id_copy | qualification | employment_contract | disability_verification | other
title                CharField
description          TextField, blank
file                 FileField (employee_documents/%Y/%m/)
content_type          CharField — server-sniffed (documents/validation.py), never client-trusted
size_bytes            PositiveIntegerField
uploaded_by           FK Employee, SET_NULL, null — hr_admin filing on someone's behalf vs. self-upload
history               HistoricalRecords — same audit-trail precedent as Policy/BiometricEnrollment
```
`tier` is a `@property`, not a column (§2.6). No `DELETE` restriction at the model layer (unlike `Policy`, which
retires via `archive` to protect `PolicyAcknowledgment.PROTECT`) — nothing else points at an `EmployeeDocument`,
so a real delete (used by erasure, §6.1, and by ordinary hr_admin document management) is safe.

### 4.2 `documents.DataSubjectRequest`

```
employee             FK Employee, CASCADE, related_name="data_subject_requests"
request_type          export | erasure
status                 submitted | completed | declined
requested_by           FK Employee, SET_NULL, null — usually == employee; hr_admin when filed on someone's behalf
requested_at            auto_now_add
request_notes           TextField, blank
reviewed_by             FK Employee, SET_NULL, null
reviewed_at             DateTimeField, null
resolution_notes         TextField, blank
export_file              FileField (data_subject_exports/%Y/%m/), null — populated only when an EXPORT completes
```
Constraint: one **open** (`submitted`) request per employee per `request_type` — mirrors
`onboarding.ChecklistInstance`'s "one active checklist per employee per direction" partial-unique shape, for the
same reason (don't let a second identical request pile up while the first is unactioned).

### 4.3 `core_hr.Dependant`

```
employee         FK Employee, CASCADE, related_name="dependants"
first_name        CharField
last_name          CharField
relationship        spouse | child | parent | other
date_of_birth       DateField, null, blank
id_number           CharField, blank — third party's, Restricted (§2.9)
notes                TextField, blank
```

### 4.4 `core_hr.EmergencyContact`

```
employee          FK Employee, CASCADE, related_name="emergency_contacts"
name                CharField
relationship          CharField (free text — spouse/parent/sibling/friend/other doesn't need to be closed like
                       Dependant's, an emergency contact's relationship label is informational only)
phone                 CharField
alternative_phone      CharField, blank
email                   EmailField, blank
is_primary               BooleanField, default False
```
Constraint: at most one `is_primary=True` row per employee (partial unique, same `Q(is_primary=True)` shape as
`ChecklistInstance`'s active-instance constraint) — so "who do we call first" is unambiguous without the UI having
to enforce it client-side.

---

## 5. Access control

### 5.1 `EmployeeDocument`

| Action | Who |
|---|---|
| Create (`POST /employee-documents/`) | Self (own record) or `hr_admin` (§2.8) — enforced in the serializer's `validate()`, same shape as `RowScopedLearningSerializer` but using `IsSelfOrHRAdmin`'s boolean check instead of `has_row_access` |
| Read (list/retrieve/download) | Row-tier gated: `can_access_tier_for_target(requester, document.employee, document.tier, mode="read")` — self sees all own tiers (base `employee` role holds P/I/S/R read=True, self scope); `hr_admin` all; `auditor` all (read-only role, all tiers); `ee_manager` Sensitive+ org-wide (matches its existing S:read=True,all grant — same exposure `EmployeeVersion.disability_detail` already has); `comp_manager` Restricted org-wide (matches its R:read=True,all grant — employment contracts); `line_manager` Internal only, own team (matches its I:read=True,own_team / S:read=False / R:read=False grant) |
| Update/Delete | Self or `hr_admin` (§2.8) |
| `consent` action (`POST /employee-documents/consent/`) | Self or `hr_admin`, same shape as `identity_verification`'s `LivenessCheckViewSet.consent` |

List filtering is two-pass at demo scale (row-scope via `row_scoped_queryset`, then a Python-level tier filter
materialised back into an `id__in` queryset for pagination compatibility) — same "fine at the hundreds-of-rows
scale, a production-scale list should switch to server-side filtering" caveat `fetchAllPages`'s own docstring
already carries for this codebase.

### 5.2 `Dependant` / `EmergencyContact`

Self or `hr_admin`, full stop — both read and write (§2.8-2.9). `core_hr.permissions.IsSelfOrHRAdmin` (new,
generic — §2.8) gates object access; `get_queryset` filters the list to the caller's own rows unless they hold
`hr_admin`, same shape as `policies.PolicyAcknowledgmentViewSet.get_queryset` (detail lookups unfiltered, so a
non-owner gets a 403 via the permission class rather than a queryset-driven 404 — no secrecy reason here to hide
existence, unlike `Policy`'s draft-hiding).

### 5.3 `DataSubjectRequest`

| Action | Who |
|---|---|
| Create | Self, or `hr_admin` filing on someone's behalf (§6.2 covers why hr_admin-filed exists) |
| List/read | Self (own requests); `hr_admin` all; `auditor` all (read-only, all-scope role) — via `row_scoped_queryset` |
| `complete` / `decline` actions | `hr_admin` only |
| `download` (the export artifact, once completed) | Same authenticated-`FileResponse` pattern as `PolicyViewSet.download` — self or `hr_admin`, gated by `get_object()` running the same permission-filtered queryset |

---

## 6. The POPIA export/erasure workflow

### 6.1 Erasure is an explicit allow-list, not a `RetentionRule`-driven delete

This is the one place the spec has to hold two things in tension at once: POPIA gives a data subject the right to
request erasure, and the employment-exit-states spec (§6.3) established that this system's access cascade **never
deletes** — it withdraws access and leaves history intact, because employment history, audit trail evidence and
statutory records must survive a person leaving (or, here, requesting erasure) regardless. A generic "erasure
deletes whatever a `RetentionRule` doesn't protect" implementation would be actively dangerous: it would delete
`EmploymentEvent`/`EmploymentChange` unless someone remembered to keep their RETAIN rule (seeded in
`core_hr/migrations/0011...`) forever correct, and a misconfigured or missing rule would silently produce exactly
the CCMA-exposure/audit-integrity problem the exit-states spec was written to prevent.

So `documents.services.execute_erasure` does not consult `RetentionRule` at all. It is a hardcoded allow-list —
the only things an erasure request can ever touch, no matter what:

1. Every `documents.EmployeeDocument` row (and its file) for the employee — deleted.
2. Every `core_hr.Dependant` and `core_hr.EmergencyContact` row for the employee — deleted.
3. Three specific `core_hr.Employee` fields — `preferred_name`, `personal_email`, `phone` — cleared. These are
   exactly the "ESS-editable fields (contact details, self-ID via consent flow)" `RBAC-Roles.md` already
   identifies as the base `employee` role's own write scope — if the employee could freely edit it themselves,
   it's optional profile data, not a statutory or contractual record.
4. Any active `ConsentRecord` with `purpose=EMPLOYEE_DOCUMENTS` for the employee — withdrawn (not deleted;
   `withdraw_consent` already preserves the record, matching `ConsentRecord`'s own "withdrawal never deletes"
   design).

**Never touched, unconditionally, regardless of any rule**: `national_id_number`, `passport_number`,
`date_of_birth`, `work_email`, `hire_date`, `employee_number` (statutory/contractual identity fields);
`EmployeeVersion` history including `race`/`gender`/`disability_status` (EE-reporting data under a legal
obligation, not consent, per `ConsentRecord.LawfulBasis.LEGAL_OBLIGATION_EEA`); `EmploymentEvent`,
`EmploymentChange`, `AuditLogEntry` (RETAIN-ruled or append-only by construction). If a future erasure request
genuinely needs to reach further, that is a conscious spec change to this allow-list, not a config toggle.

### 6.2 Both request types go through `hr_admin` review — not just erasure

Export carries none of erasure's retention tension, but the workflow still routes it through `hr_admin` action
rather than auto-generating on submit, for two reasons: one queue/one mental model is simpler than "export is
instant, erasure needs a human," and — concretely — an export bundle should be assembled and handed over
deliberately (POPIA also expects the *response* to a data-subject request to be tracked, not just the data itself
handed out silently). The `complete` action behaves differently per `request_type` (generates and attaches an
export file, or executes §6.1's allow-list) but the review/action shape is identical either way.

### 6.3 Why `hr_admin`-filed requests exist: the exit cascade already logs a departed employee out

C1 part 3's access cascade (`core_hr/exits.py::_withdraw_access`) disables `employee.user.is_active` on any ending
change type. A terminated employee therefore cannot log into ESS to submit their own request — "an employee (or
ex-employee, if still reachable)" in the backlog item is honoured by letting `hr_admin` file a
`DataSubjectRequest` with `employee` set to the departed person and `requested_by` set to the filing `hr_admin`
(the same `actor`-vs-`subject` split `rbac_audit.consent.record_consent` already uses for "capturing consent on
someone's behalf"). The real-world trigger for that hr_admin-initiated filing is an out-of-band channel (an email,
a phone call) — this system doesn't need a passwordless portal to honour the right, it needs the filing path to
not assume the requester is still an active session, and now it doesn't.

### 6.4 Export scope: real, but honestly bounded

`documents.services.generate_export` assembles: the employee's own `Employee`/`EmployeeVersion` history (via
`core_hr`, which every app may import directly), their `EmployeeDocument` metadata (type/title/upload date — not
necessarily re-embedding every file's bytes into one JSON blob), `Dependant`/`EmergencyContact` rows, their
`ConsentRecord` history, and their own `DataSubjectRequest` history — everything `documents` + the kernel can
assemble without a new peer-app import. It deliberately does **not** reach into `learning`/`performance`/
`compensation`/`recruitment` for a fully exhaustive personal-data export across every module — that would need a
`queries.py` seam per module and is real, scoped-out follow-up work, not a corner cut silently. This spec records
that boundary explicitly rather than claiming completeness the implementation doesn't have.

---

## 7. Retention scopes

Seeded in a new `documents` migration, same shape as `core_hr/migrations/0011_seed_employment_retention_rules.py`:

| Entity | Action | Period | Reasoning |
|---|---|---|---|
| `documents.EmployeeDocument` | RETAIN | 84 months (documented, no runtime effect for `retain`) | Mirrors the exit-states spec §7 reasoning for `EmploymentEvent`/`EmploymentChange`: nobody has proposed an anonymise/delete policy for ID copies, contracts or qualification evidence, so this turns "nobody decided" into a recorded decision rather than silence. 84 months (7 years) is chosen over BCEA's 3-year floor because employment contracts and qualification evidence are the kind of record a CCMA dispute or SETA audit can reach back further for than a straightforward termination-reason record would — a deliberately more conservative number than `EmploymentEvent`'s 36, not the same one copied blind. |
| `core_hr.Dependant` | DELETE | 1 month | Unlike documents, a dependant record has no standalone evidentiary value once detached from an active benefits/medical-aid relationship — it exists to serve the *current* employee relationship. A short window (rather than RETAIN) reflects that this is genuinely disposable once stale, while still not deleting it the instant it goes untouched (an active employee's dependant list doesn't change monthly, so 1 month only fires for what's actually abandoned — e.g. left behind by an erasure-adjacent path or a data-quality cleanup, not normal use). No handler is registered yet (§8) — this is the same "recorded decision, executor is follow-up work" posture the pre-existing rules already carry. |
| `core_hr.EmergencyContact` | DELETE | 1 month | Same reasoning as `Dependant`. |

No handler is registered for any of the three in `rbac_audit/retention.py`'s `_HANDLERS` registry yet — exactly
like most of the rows seeded by `0007_seed_default_retention_rules.py`/`0011_...`, a rule with no handler reports
`no_handler` and changes nothing at runtime (`retention.py`'s own module docstring: "a rule with no registered
handler is reported as `no_handler`, never guessed at"). Registering the actual sweep is out of this slice's
scope, consistent with how `EmploymentEvent`/`EmploymentChange`'s RETAIN rules also have no handler and don't need
one (RETAIN is always skipped). `Dependant`/`EmergencyContact`'s DELETE rules **do** eventually need a handler for
the number to mean anything operationally — recorded here as a known, named gap rather than left implicit.

---

## 8. Testing

Mirrors `core_hr/test_exits.py`'s and `onboarding/test_checklists.py`'s shape: service-layer tests for every
`DocumentError`/erasure-allow-list edge (consent required and missing, consent required and present, wrong actor,
already-open request blocks a second one, erasure never touches `EmploymentEvent`/`AuditLogEntry`/the three
protected `Employee` fields even when asked), plus API-level tests asserting the role matrix in §5 end-to-end
(self can read/write own; `hr_admin` can act on anyone's; `line_manager` gets Internal-only, own-team, no
Sensitive/Restricted; a stranger role gets 403/empty list; the `download` actions require the same permission as
`retrieve`). `documents/test_api.py` for the API surface, `documents/tests.py` for services, matching every
existing app's file-naming convention.

---

## 9. Known boundaries

- **Export is scoped to `documents` + `core_hr` + `rbac_audit`, not every module** (§6.4) — a genuinely exhaustive
  POPIA export needs a `queries.py` seam per app that holds personal data (`learning`, `performance`,
  `compensation`, `recruitment` at minimum). Recorded as real follow-up work, not silently incomplete.
- **`Dependant`/`EmergencyContact` retention has no executor** (§7) — the rule exists, nothing sweeps against it
  yet, same posture several pre-existing rules already carry.
- **No line-manager visibility into a report's emergency contact** (§2.8) — considered and deliberately deferred
  to keep this slice's scope matched to the brief's stated self-service + hr_admin framing; a real gap if a
  "manager needs to reach someone in a crisis" use case gets prioritised later.
- **`EmployeeDocument` has no versioning** — unlike `Policy`, a re-upload of, say, a renewed ID copy is a new row,
  not a new version of the same logical document. `Policy`'s versioning exists because publishing/archiving state
  transitions matter for policy compliance tracking; nothing analogous applies to "a photo of someone's ID," so
  the simpler shape (one row per upload, superseded ones just sit alongside newer ones or get deleted by
  hr_admin) was chosen deliberately rather than copied from `Policy` by default.
