[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

# Generated API contracts: migration pattern

**Added:** 2026-08-28, as P0.1 of `latest_todo.md` (source: `latest_critique.md`). `ProbationPage.tsx` and
`ExitInterviewsPage.tsx` are the first two screens migrated; use them as the worked example.

## The problem

`src/api/types.ts` has long carried hand-maintained interfaces for API request/response shapes, alongside
presentation-only label maps for enum values. A hand-maintained interface drifts silently from the real backend
serializer — nothing fails when a field is renamed, removed, or gains a new required value, since the frontend and
backend copies of the shape are two independent sources of truth.

`src/api/generated-types.ts` is machine-generated from the backend's OpenAPI schema
(`npm run generate:api-types`) and does not drift. It is unpleasant to import directly, though: types are nested
several levels deep under `components['schemas'][...]`, and it also contains full request/response envelopes for
every endpoint in the system, not just the ones a given page needs.

## The pattern

1. **`src/api/contracts.ts`** is a small, flat facade re-exporting only the generated schema types a screen
   actually needs, under a stable, short name:
   ```ts
   import type { components } from './generated-types'
   export type ProbationPeriod = components['schemas']['ProbationPeriod']
   export type ProbationStatus = components['schemas']['ProbationPeriodStatusEnum']
   ```
   Pages import from `api/contracts.ts`, never from `api/generated-types.ts` directly, and never redeclare the
   shape by hand.

2. **`src/api/contract-labels.ts`** holds presentation-only label maps (`Record<EnumType, string>` for rendering a
   human-readable string) keyed against the facade's enum types. These stay out of both `contracts.ts` (transport
   declarations only, so it is trivially diffable against the generator's own output) and `types.ts` (legacy
   handwritten declarations). Because each label map is `Record<GeneratedEnum, string>`, TypeScript itself fails
   the build the day the backend adds or removes an enum value and the label map isn't updated to match — the
   generator's schema becomes the enforcement mechanism, not a comment or a test someone has to remember to write.

3. **Delete the superseded declarations from `src/api/types.ts`** once a screen's migration is complete — do not
   leave the old interface in place "just in case." A leftover handwritten copy is exactly the drift risk this
   migration exists to remove, and its presence invites a future edit to (wrongly) target it instead of the
   generated schema.

4. **Register the migrated module in `scripts/check-contract-imports.mjs`** (`MIGRATED_MODULES`), listing the
   handwritten names it must never import from `api/types` again. `npm run lint` runs this check (via
   `check:contracts`) after `oxlint`, so CI's existing Lint step catches a regression — e.g. someone reverting a
   merge conflict back onto the old handwritten type — without needing a dedicated workflow step.

## What does *not* migrate

Not every type in `api/types.ts` has a generated counterpart. Aggregate/dashboard response shapes built by a
plain Django function view (not a `ModelViewSet`/serializer) usually have no OpenAPI schema entry at all —
`ProbationCompletionDashboard`, `ExitInterviewDashboard`, and similar breakdown/dashboard types are legitimately
handwritten and out of scope for this migration. Check `generated-types.ts` for the shape's name before assuming
it should move; if it isn't there, it isn't a candidate.

## Checklist for the next module

- [ ] Inventory the transport types, enums and labels the screen actually uses.
- [ ] Confirm each one has a real entry in `generated-types.ts`'s `components['schemas']`; skip ones that don't
      (see above).
- [ ] Add the needed re-exports to `api/contracts.ts`.
- [ ] Add any presentation-only label maps to `api/contract-labels.ts`, typed against the facade's enum, not a
      hand-copied union.
- [ ] Update the screen's imports to pull from the facade/labels file instead of `api/types.ts`.
- [ ] Delete the now-unused handwritten declarations from `api/types.ts`.
- [ ] Add the module to `MIGRATED_MODULES` in `scripts/check-contract-imports.mjs`.
- [ ] Run `npx tsc --noEmit`, `npm run lint`, `npm run build`.
