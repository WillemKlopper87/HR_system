# Super Smart Admin Guide

**Sentech HCM — deployment, setup, day-to-day management, and accounts.** Written for whoever runs this
system, assuming comfort with a terminal and Docker. For the HR-user-facing walkthrough, see
`docs/hr-user-guide/HR-USER-GUIDE.md`. For what's automatically verified vs. what still needs a human sign-off,
see `docs/RELEASE-EVIDENCE.md`. For per-model data-retention status, see `docs/RETENTION-MATRIX.md`.

---

## Quick reference

| I need to... | Do this |
|---|---|
| Check if the system is up | `curl http://<host>/healthz` (process alive) and `/readyz` (DB + cache actually reachable) |
| See recent logs | `docker compose logs -f backend` (add `worker`/`beat`/`frontend` for the others) |
| Run a one-off Django command | `docker compose exec backend python manage.py <command>` |
| Deploy a new version | See [Deploying a new version](#deploying-a-new-version) |
| Roll back a bad deploy | Re-pin `IMAGE_TAG` to the previous SHA and redeploy — see `docs/RUNBOOK.md` |
| Add a real employee | `python manage.py import_employees <file.csv>` — see [Getting real people into the system](#getting-real-people-into-the-system) |
| Give someone a login | Django admin (`/admin/`) — see [Accounts, logins and roles](#accounts-logins-and-roles) |
| Reset a forgotten password | Django admin → Users → their username → "this form does not display the raw password..." link |
| Back up the database | `docker compose exec -T db pg_dump -U hcm -Fc hcm > backup.dump` — full procedure in `docs/RUNBOOK.md` |

---

## 1. First-time setup

This bootstraps a brand-new environment from nothing. Do this once per environment (dev, staging, prod).

### 1.1 Create your `.env`

```bash
cd hcm
cp .env.example .env
```

Then edit `.env` and replace **every** `change-me` with a real value:

```bash
# generates a strong random value you can paste in
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

You need real values for `DJANGO_SECRET_KEY`, `ASSESSMENT_WEBHOOK_SECRET`, and `POSTGRES_PASSWORD` at
minimum. **This isn't optional if `DJANGO_DEBUG=0`** — the app will refuse to start at all with a
`change-me`-style secret once debug mode is off (see `config/settings.py`'s `_require_production_secret`).
That's deliberate: it's better to fail loudly at boot than silently run a production system with a
guessable secret.

Leave `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` / `DJANGO_SECURE_HSTS_PRELOAD` at `0` until you've actually
confirmed every subdomain of your production domain serves exclusively over TLS — `PRELOAD` in particular is
effectively a one-way decision (it gets baked into browsers). Don't flip these on a guess.

### 1.2 Bring the stack up

```bash
docker compose up -d
```

This starts, in order: `db` (PostgreSQL) and `redis` become healthy first, then a one-shot `migrate` service
runs every pending migration and exits, and only once that succeeds do `backend`, `worker` and `beat` start.
`frontend` (nginx) comes up last, once `backend` reports healthy on `/readyz`. You don't need to run migrate
yourself — it's wired into the dependency chain, not something to remember.

Check it worked:

```bash
docker compose ps        # everything should say "healthy", migrate should say "Exited (0)"
curl http://localhost:8080/       # frontend, if using the default port mapping
```

### 1.3 Get into Django admin (`/admin/`)

The app's own roles (hr_admin, recruiter, etc. — see [§4](#accounts-logins-and-roles)) are **separate** from
Django's own admin-site access, which is gated by the `is_staff` flag on the underlying login account. No
seeded account has this by default (not even the demo `hradmin` login) — for the very first real
administrator, create one directly:

```bash
docker compose exec backend python manage.py createsuperuser
```

This asks for a username, email and password, and grants full Django-admin access. Use this account to set
up everyone else's access via `/admin/` (see §4) — you generally don't want more than one or two accounts
with raw superuser access long-term; give ordinary hr_admin/sysadmin staff `is_staff=True` without
`is_superuser` once they have real `RoleAssignment` rows instead.

### 1.4 Load your data

**For a demo/eval environment**, seed synthetic data:

```bash
docker compose exec backend python manage.py seed_demo_data
```

This creates ~150 synthetic employees, demo logins (`hradmin`/`hradmin123`, `manager`/`manager123`, etc. —
see `hcm/README.md` for the full list), sample requisitions/applicants, a performance period, and more.
**Never run this against a real production database** — it's meant for local dev, demos and CI only.

**For a real deployment**, import your actual employee data instead — see the next section.

---

## 2. Getting real people into the system

### 2.1 Bulk-importing existing employees

```bash
docker compose exec backend python manage.py import_employees /path/to/employees.csv
```

Accepts `.csv` or `.xlsx`. Required columns per row:

| Column | Notes |
|---|---|
| `employee_number` | Must be unique |
| `first_name`, `last_name` | |
| `date_of_birth`, `hire_date` | Must parse as dates; DOB must be before hire date |
| `work_email` | Must be unique and a valid email |
| `department_code` | Must match an existing `Department.code` — see Org Structure |
| `occupational_level_code` | Must match one of the six statutory EE levels |
| `location_code` | Must match an existing `Location.code` |

Optional: `preferred_name`, `national_id_number`, `personal_email`, `phone`, `job_grade_code`,
`employment_status`, `citizenship_status`, `race`, `gender`, `disability_status` (all default sensibly —
demographics default to "not disclosed" if omitted, never guessed).

The command reports how many rows imported and prints every skipped row with its reason — a duplicate
`employee_number`, an unrecognised `department_code`, etc. **It does not partially apply a bad row**; a
row that fails is skipped entirely, not half-written.

**Import creates the employee record only — not a login.** See §4 to give someone access.

### 2.2 One employee at a time (recruitment)

Outside a bulk import, the normal way a new employee record appears is through the recruitment pipeline: a
requisition → an applicant → an accepted offer → hire. There's no separate "just add an employee" button —
this is deliberate, so every real employee has a recruitment trail rather than appearing from nowhere. See
`docs/hr-user-guide/HR-USER-GUIDE.md` §4 for the HR-facing walkthrough of that flow.

---

## 3. Accounts, logins and roles

Three separate things, easy to conflate:

1. **A Django `User`** — the username/password someone actually logs in with.
2. **An `Employee`** — the HR record (name, department, employee number, etc.).
3. **A `RoleAssignment`** — what that employee is allowed to *do* in the app (hr_admin, recruiter, line
   manager, ...).

An `Employee` can exist with no `User` at all (e.g. freshly bulk-imported, or someone who should never log
in themselves). A `User` with no `RoleAssignment` can log in but sees almost nothing — every meaningful
permission in the app comes from an active role, not just from being authenticated.

### 3.1 Giving someone a login

There's no frontend screen for this yet — use Django admin (`/admin/`), signed in as your superuser account:

1. **Users → Add user.** Set a username and a temporary password. Leave `is_staff`/`is_superuser` unchecked
   unless this person also needs Django-admin access themselves (ordinarily only your other sysadmins do).
2. **Core_hr → Employees**, find the person, open their record, and set the **User** field to the account
   you just created.
3. **Rbac_audit → Role assignments → Add role assignment.** Pick the employee and the role that matches
   their job (see the table below). `granted_by` and `granted_at` are recorded automatically.

They can now sign in at `/login` with the username/password from step 1.

### 3.2 The roles

| Role | Sees | Typical holder |
|---|---|---|
| `employee` | Only their own record (self-service) | Everyone, by default |
| `line_manager` | Their own team; demographic aggregates only, never individual pay | A manager with direct reports |
| `hr_admin` | Everything, full read/write on core HR data | HR staff |
| `recruiter` | The recruitment module org-wide; no performance/comp access | Talent acquisition |
| `comp_manager` | Pay bands, comp proposals, benefits config | Compensation & benefits |
| `ee_manager` | EE reporting, self-ID campaign, EEA sign-off | Employment Equity officer |
| `auditor` | Read-only, everywhere, including the audit log — every auditor read is itself logged | Internal/external audit |
| `accounting_officer` | Final EEA2/EEA4 sign-off only | The PFMA-designated accounting officer |
| `sysadmin` | Technical operations, user/role mapping — **no standing access to Sensitive/Restricted business data** | You |

Full detail (field-tier grants, row-scope reasoning) is in `RBAC-Roles.md`. **A role can be revoked** (set
`revoked_at` on the `RoleAssignment` row rather than deleting it) — deleting the row loses the audit trail
of who had access to what and when, which is exactly the thing an auditor role exists to check.

An employee can hold more than one role at once (e.g. a manager who is also the EE manager) — access is the
union of everything their active roles grant.

### 3.3 Resetting a password

Django admin → Users → find their username → open it → the password field shows "raw passwords are not
stored... you can change the password using **this form**" — click that link, set a new one, save. There is
no self-service "forgot password" flow yet; this is the only way.

### 3.4 Payroll step-up (TOTP)

`comp_manager` and `hr_admin` need a second factor (a real authenticator app, RFC 6238 TOTP) the first time
they touch a Restricted-tier payroll screen (pay bands, comp proposals, remuneration records) — this is
separate from their ordinary login and can't be bypassed by an admin; the employee enrols it themselves on
first visit. If someone loses their device, there's no admin "reset MFA" button yet — this would need a
direct database intervention (`rbac_audit.TOTPDevice`) until one exists; treat that as rare enough to handle
by hand, and log what you did.

### 3.5 When someone leaves: revoking access

Don't manually deactivate a `User` or delete `RoleAssignment` rows for an offboarding employee — use the
proper **Employment Changes** workflow instead (`docs/hr-user-guide/HR-USER-GUIDE.md` §7). Confirming an
exit there is what triggers the actual access cascade (role assignments revoked, biometric enrolment
dropped, offboarding checklist created) as one deliberate, audited action — not a scattered set of manual
edits an auditor later has to reconstruct.

---

## 4. Deploying a new version

Two topologies, one file each:

- **`docker-compose.yml`** — builds every image from source. Use this for local dev; not for production
  (an operator shouldn't need a build toolchain on the production host, and a source build isn't provably
  the same artifact CI tested).
- **`docker-compose.prod.yml`** — an override that replaces every build with a pinned, pre-built image.
  **This is the target shape, not yet a fully working path** — there is no CI job today that actually builds
  and pushes images to a registry (tracked in `docs/RELEASE-EVIDENCE.md`). Until that exists, production
  deploys still mean building on the host, same as dev, just with `docker-compose.prod.yml` not yet usable
  for its intended purpose.

Once that CI job exists, the intended flow (already working, already tested against a real
`docker compose up`) is:

```bash
export HCM_IMAGE_REGISTRY=ghcr.io/<your-org>
export IMAGE_TAG=<git-sha-that-passed-ci>     # never "latest" — always a specific, deliberate SHA
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Before any deploy whose migration touches an existing column or table**, take a fresh backup — don't rely
solely on the nightly one:

```bash
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-hcm}" -Fc "${POSTGRES_DB:-hcm}" > hcm-pre-deploy-$(date +%Y%m%d%H%M).dump
```

**Rollback** is the same command with `IMAGE_TAG` re-pinned to the previous known-good SHA. This works
*because* every migration in this codebase is expand/contract (additive first, never drop/rename in the
same release a rollback might be needed for) — the old code keeps running against the current schema with
no schema-side rollback needed. Single-node Compose has no second warm instance to shift traffic to, so
both directions are **redeploys measured in minutes, not an instant traffic-shift** — say that out loud to
whoever's running a rollback under pressure.

Full procedure, including the reasoning and known gaps, lives in `docs/RUNBOOK.md`'s "Deploy & rollback"
section.

---

## 5. Ongoing management

### 5.1 Health

- `GET /healthz` — is the process alive at all. What a load balancer's *liveness* probe should hit; it never
  checks a dependency, so a slow database query can't make it flap.
- `GET /readyz` — can this instance actually serve traffic (database + cache both reachable). Point
  orchestration's *readiness* probe here. Returns which specific check failed if it's down.
- `worker`/`beat` don't serve HTTP at all — their health is `celery inspect ping` and a schedule-freshness
  check respectively, both wired into `docker-compose.yml`'s own healthchecks. `docker compose ps` shows
  "healthy"/"unhealthy" for all five services the same way.

### 5.2 Logs

```bash
docker compose logs -f backend    # or worker / beat / frontend / db / redis
```

Plain stdout/stderr, no extra log-shipping infrastructure required — whatever your host's container runtime
already captures is enough. Set `SENTRY_DSN` in `.env` to also get exception tracking (off by default;
`send_default_pii` is hardcoded false — no employee data ever reaches Sentry).

### 5.3 The retention job

Runs automatically, daily at 02:00 SAST (`CELERY_BEAT_SCHEDULE` in `config/settings.py`). To see what it
would do without changing anything:

```bash
docker compose exec backend python manage.py run_retention --dry-run
```

Not every `RetentionRule` has an enforcement handler yet — a rule with none logs a warning and does nothing,
deliberately (an unenforced rule is safer than a wrong one). See `docs/RETENTION-MATRIX.md` for exactly
which entities are actually enforced today, and which known gaps are recorded rather than guessed at.

### 5.4 Backups

Automated nightly backup is policy (ADR-005); the concrete commands — database (`pg_dump`), media (the
`hcm_media` Docker volume), restore, and the quarterly restore-rehearsal procedure — are all in
`docs/RUNBOOK.md`. Read that file before your first real restore, not during an incident.

### 5.5 Dependency updates

`.github/dependabot.yml` watches `hcm/backend` (pip), `hcm/frontend` (npm) and the CI workflow's own pinned
GitHub Actions, weekly, grouped by minor/patch — security patches ship immediately regardless of that
schedule. Every resulting PR runs the same `hcm-ci.yml` gate as any other change; there's no fast-tracked or
unreviewed path for a dependency bump.

### 5.6 CI gates

`hcm-ci.yml` runs on every push/PR: backend tests on both SQLite and PostgreSQL, a migration-drift check, a
production-secret fail-fast check, an OpenAPI-contract-drift check, frontend lint/typecheck/build, and the
full Playwright e2e suite. **GitHub Actions is currently billing-blocked for this repo** — every job fails
in seconds regardless of the code — so none of this runs automatically right now; the same commands run
locally (see each job's `run:` steps in `.github/workflows/hcm-ci.yml`) are the actual gate until that's
resolved. Don't mistake "CI is red" for "the code is broken" without checking which one it is.

---

## 6. Where to look next

| Question | Document |
|---|---|
| "Is X actually verified, or just claimed?" | `docs/RELEASE-EVIDENCE.md` |
| "What happens to this data eventually?" | `docs/RETENTION-MATRIX.md` |
| "How do backups/restores/deploys actually work, step by step?" | `docs/RUNBOOK.md` |
| "What can each role see and do, exactly?" | `RBAC-Roles.md` |
| "How do I run this locally for development?" | `hcm/README.md` |
| "What shipped recently, and why?" | `docs/SESSION-STATE.md` |
| "How does an HR user actually use the app?" | `docs/hr-user-guide/HR-USER-GUIDE.md` |
