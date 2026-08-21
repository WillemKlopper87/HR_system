# Session state — 2026-08-21

Written as a resume point. The machine has killed background agents three times
today (VS Code plugin updates), so this records where things stand and what a
next session should pick up. **Everything described as done is committed and
pushed** — `origin/master` is current.

## Where the work is

`HEAD = 74e2697`, pushed. Working tree clean.

## Shipped today

| Item | Commits | State |
|---|---|---|
| **C1 pt 1** — Position/establishment | through `b34bfb7` | Done, pushed |
| **C1 pt 2** — Contract end-dates | through `4466847` | Done, pushed |
| **Org chart** `/org-chart` | `2a3be95`, `1ab1ea7` | Done, pushed |
| **C1 pt 3 slice 1** — exit states + access cascade | `608bd31` (spec), `cdfbac4` | Done, pushed |
| **Contract lapse → cascade** | `74e2697` | Done, pushed |
| Sidebar redesign, audit-log flake, notification badge, H3 docs split | various | Done, pushed |
| `docs/MVP-Backlog.md`, org-chart visibility decision | `3527db9`, `b228543` | Done, pushed |

**Full backend suite: 774 passing, verified at `74e2697`** (2026-08-21, ~10 min
run). No fallout from routing contract lapse through the cascade.

## Do this first in a new session

1. **Run the e2e suite** (`npm test` in `hcm/frontend`). Ports 8000/5173 are
   often held by an unrelated project — repoint `playwright.config.ts`,
   `vite.config.ts` and `e2e/backend-server.mjs` to free ports, set
   `DJANGO_CSRF_TRUSTED_ORIGINS` via env, then **revert all three** and confirm
   byte-identical before committing.
2. `manage.py check` and `makemigrations --check --dry-run`.

## Next up (agreed sequence)

Sequencing is by **demoable lifecycle journey**, not technical dependency —
see `docs/MVP-Backlog.md` Part B and the memory note on MVP direction.

1. **C1 pt 3 slice 2** — API + frontend for the exit states (propose, confirm,
   cancel, the suspension/lift flow). Backend service layer is done and tested;
   nothing is exposed over HTTP yet.
2. **C1 pt 3 slice 3** — onboarding/offboarding checklists. Decided shape:
   versioned templates mirroring `AgreementTemplate`, so HR can change the
   process after the demo without a deploy.
3. **C2** — employee documents. Closes the third of five lifecycle breaks.

## Blocked on a decision, not effort

- **Leave / absence management.** Ceded to SAP as "mirror only", but nothing
  exists — not even the mirror — while the Policy Library ships a Leave Policy
  document with no system behind it. Biggest demo win available. Needs the
  cede-to-SAP decision revisited before anyone builds it.

## Known defects (all pre-existing, none from today's work)

- **ESS phone edit does not persist across reload** (`ess-policies.spec.ts`).
  Real, reproduced at base commit, Sprint-15 territory.
- `core-hr.spec.ts` `settled()` timing flake.
- Parked residuals from C1 pt 2: `ee_manager`/`recruiter`/`comp_manager` can
  read contract-renewal decisions spec §6 doesn't grant them; the two write
  actions serialise their response bypassing the tier gate; no
  `@extend_schema` on either action, so drf-spectacular infers the wrong body.

## Environment notes

- **GitHub Actions is billing-blocked** — every job fails in seconds. Push
  directly; local suites are the gate. Not a code problem.
- Background agents have been killed mid-task three times. Commit checkpoints
  early rather than holding a large uncommitted change set.
- A separate AI agent runs a Django server for an **unrelated** project on port
  8000. Do not kill it; use other ports.
