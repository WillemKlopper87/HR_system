[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

### C1 — Establishment & lifecycle
**Status:** part 1 of 3 done (2026-08-19, commit `b2ad0c0` + final-review fixes) — see `ROADMAP-2026-08.md`'s C1 row for full detail and `docs/superpowers/specs/2026-08-19-position-establishment-design.md` for the design spec. Parts 2 and 3 each still need their own brainstorm/spec before starting.
- [x] `Position` (approved vs filled, post number, vacancy rate); requisitions tied to vacant posts — done: new `establishment` app (post-numbered `Position`, configurable approval chain, `Requisition.positions` M2M, derived occupancy on `EmployeeVersion.position`, `/positions` page)
- [ ] `contract_end_date` / `probation_end_date` + reminders; onboarding/offboarding checklists with termination cascades — not started, needs its own spec

