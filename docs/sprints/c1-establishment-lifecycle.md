[← Back to the sprint plan index](../../Sprint-Plan-HCM-System.md)

### C1 — Establishment & lifecycle
**Status:** all three parts done. Part 1: 2026-08-19, commit `b2ad0c0` + final-review fixes — see
`ROADMAP-2026-08.md`'s C1 row and `docs/superpowers/specs/2026-08-19-position-establishment-design.md`. Part 2:
contract end-dates + renewal decisions, spec `docs/superpowers/specs/2026-08-20-contract-end-date-tracking-design.md`.
Part 3 shipped in three slices: exit states + access cascade (spec
`docs/superpowers/specs/2026-08-20-employment-exit-states-design.md`), the API/frontend for that state machine,
and onboarding/offboarding checklists (spec
`docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md`) — a new `onboarding` app with
versioned templates, automatic instance creation off `hire()` and off an exit's execution (via
`core_hr/lifecycle_hooks.py`, the same registry pattern as `access_cascade.py`), and task completion gated by
owner role + reporting chain.
- [x] `Position` (approved vs filled, post number, vacancy rate); requisitions tied to vacant posts — done: new `establishment` app (post-numbered `Position`, configurable approval chain, `Requisition.positions` M2M, derived occupancy on `EmployeeVersion.position`, `/positions` page)
- [x] `contract_end_date` / `probation_end_date` + reminders — done (C1 part 2)
- [x] Employment exit state machine (suspend/dismiss/resign/retire/…) + access cascade (roles revoked, login disabled, biometric enrolment suspended) — done (C1 part 3 slices 1-2)
- [x] Onboarding/offboarding checklists with termination cascades — done (C1 part 3 slice 3): versioned `ChecklistTemplate`, per-employee `ChecklistInstance` created automatically on hire (onboarding) and on an ending-type `EmploymentChange` executing (offboarding), `/checklists` + `/checklist-templates` pages

