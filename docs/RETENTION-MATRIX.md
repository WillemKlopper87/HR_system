[← Back to the sprint plan index](../Sprint-Plan-HCM-System.md)

# Retention matrix

**Added:** 2026-08-28, closing HR_Code_report.md's M7 ("maintain a data-retention matrix for each model and
file field... test both row and blob deletion"). This is the matrix; the accompanying test coverage lives
next to each handler (`recruitment/test_retention.py`, `rbac_audit/test_retention.py`).

## How this system's retention actually works

- `rbac_audit.RetentionRule` is a per-`entity_type` row: a period in months, an action
  (`retain` / `delete` / `anonymise`), and `active`. Seeded via data migrations, editable in Django admin.
- `rbac_audit.retention.run_retention()` (scheduled daily at 02:00 SAST, `config/settings.py`
  `CELERY_BEAT_SCHEDULE`) walks every active, non-`retain` rule and looks up a **registered handler** for
  its `entity_type`.
- **A rule with no registered handler does nothing but log a warning.** This is a safe default — better an
  unenforced policy than a wrong one — but it means a rule existing is not evidence the policy is enforced.
  Check the "Handler" column below before assuming a row here means anything actually happens.
- Handlers are registered per-app from `AppConfig.ready()` (`rbac_audit/retention.py`'s own module
  docstring explains the pattern); `retain` rules are always skipped by the executor regardless of whether
  a handler exists, since there's nothing to execute.

## Models and file fields

| Entity / field | Rule (seeded) | Handler | Deletes the file too? | Notes |
|---|---|---|---|---|
| `rbac_audit.AuditLogEntry` | retain, 60mo | ✅ registered | n/a (no file) | Built-in handler; `retain` is a no-op by design — this row exists so the policy is a recorded, conscious choice per Data-Dictionary.md, not silence. |
| `rbac_audit.StepUpGrant` | delete, 1mo | ✅ registered | n/a (no file) | Ephemeral by design (15-min grants); deletes the row outright. |
| `recruitment.Applicant` + `.resume` | anonymise, 12mo (or delete, if the rule is switched) | ✅ registered | ✅ **fixed 2026-08-28** | Was the concrete M7 finding: anonymisation cleared every PII field except the résumé file itself, leaving the original person's CV — real name, contact details, work history — on disk indefinitely under an "anonymised" row. Both the anonymise and delete code paths now call `resume.delete(save=False)` before persisting; `recruitment/test_retention.py` proves the underlying storage object is actually gone, not just the DB field. |
| `core_hr.EmploymentEvent` | retain, 36mo | — (retain, no handler needed) | n/a (no file) | Documents the BCEA 3-year floor; no runtime effect by design. |
| `core_hr.EmploymentChange` | retain, 36mo | — (retain, no handler needed) | n/a (no file) | Same reasoning — proposer/confirmer/reason provenance for a contested dismissal. |
| `core_hr.Dependant` | delete, 1mo | ❌ **not registered — real, deliberately-not-guessed gap** | — | See "Known gap" below. |
| `core_hr.EmergencyContact` | delete, 1mo | ❌ **not registered — same gap** | — | See "Known gap" below. |
| `documents.EmployeeDocument` + `.file` | retain, 84mo | — (retain, no handler needed) | n/a | Deliberately longer than EmploymentEvent's 36mo — a CCMA dispute or SETA audit can reach back further for a contract/qualification document than a plain termination reason. |
| `documents.DataSubjectRequest` + `.export_file` | **no rule seeded** | ❌ none | ❌ | A POPIA export bundle sitting in storage indefinitely with no retention policy at all is the same class of gap M7 flags — this should get an explicit rule (retain is a legitimate choice here, but it should be a *recorded* one, not an absence). Not fixed in this pass; needs a lawful-basis/retention-period decision, not a guess. |
| `ee_reporting.EEPlan` / `.EEPlanMeasure` / `.EEPlanProgressSnapshot` | retain, 60mo | — (retain, no handler needed) | n/a (no file on Plan/Measure/Snapshot) | EE Regulations 2025 reg. 9(15): 5 years post-expiry. |
| `ee_reporting.EEForumMeeting` + `.minutes_file` | retain, 60mo | — (retain, no handler needed) | n/a | Same reg. 9(15) evidence-trail reasoning as the plan itself. |
| `ee_reporting.EEForumMember` | retain, 60mo | — (retain, no handler needed) | n/a (no file) | |
| `ee_reporting.EEReport` | retain, 60mo | — (retain, no handler needed) | n/a (no file) | EE Regulations 2025 regs. 10(14)/12(3): 5 years post-submission for both EEA2 and EEA4. |
| `learning.TrainingRecord` + `.evidence_file` | **no rule seeded** | ❌ none | ❌ | Same shape of gap as `DataSubjectRequest` above — training/B-BBEE skills-development evidence has no recorded retention decision at all. |
| `performance.PerformanceEvidence` + `.file` | **no rule seeded** | ❌ none | ❌ | Same gap. |
| `performance.AgreementSignature` + `.pdf` | **no rule seeded** | ❌ none | ❌ | This is the signed, hashed performance-agreement PDF — arguably wants the *longest* retention of anything in this table (it's the primary evidence a disputed rating or dismissal turns on), which makes the absence of an explicit rule here the most consequential single item in this matrix. |
| `policies.Policy` + `.source_file` | **no rule seeded** | ❌ none | ❌ | Same gap; likely a legitimate long-`retain`, but that should be a recorded decision. |

### Known gap: `core_hr.Dependant` / `core_hr.EmergencyContact`

The seeded rule is `delete` after 1 month, and its own migration docstring
(`documents/migrations/0002_seed_retention_rules.py`) explains the intent clearly: *"unlike documents, these
have no standalone evidentiary value once **detached from an active employee relationship**; a short window
reflects that this is genuinely disposable **once stale**."*

That is not the same thing as "delete any row whose `updated_at` is over a month old." A dependant or
emergency-contact record for a **currently employed** person is expected to sit unedited for years — nobody
updates their spouse's details every month. A handler that naively filtered on `updated_at__lt=cutoff` the
way `recruitment.Applicant`'s does would delete **current, legitimate records for active employees**, not
just detached ones. That would be a real data-loss bug shipped in the name of a privacy fix.

**Deliberately not implemented in this pass.** Registering a handler here needs an actual decision on what
"detached" means operationally — keyed to the employee's exit executing (`EmploymentChange`?), to
`EmployeeVersion.employment_status`, or to a dedicated timestamp — before it's safe to write. The rule stays
recorded-but-unenforced (its current, safe state) until that's resolved; this is a "no handler registered"
warning in the retention log, not a silent failure, so it's visible to whoever's watching for it.

## What still isn't proven end-to-end

Per HR_Code_report.md M7's own framing, none of the above proves:

- **Backup expiry** — media backups aren't retention-scoped at all yet (`docs/RUNBOOK.md`'s "what this
  runbook deliberately does not cover").
- **Legal hold** — no model or check exists to suspend a retention rule for a record under active dispute
  or investigation; a rule would delete/anonymise it on schedule regardless.
- **Deletion-failure alerting** — `run_retention`'s dry-run/result reporting exists, but nothing pages anyone
  if a scheduled run itself fails to execute (as opposed to succeeding with `error` on one entity type, which
  today's run already reports per-rule).
- **Real object storage** — every `.delete(save=False)` call here is proven against `FileSystemStorage`
  (local disk / the `media` Docker volume). The moment media moves to S3/Azure Blob (ADR-005's own noted
  future decision), the same call sites need re-verifying against whatever storage backend's actual delete
  semantics apply — Django's `Storage.delete()` API is backend-agnostic, but "prove it once" here doesn't
  mean "proven forever" once the backend changes.
