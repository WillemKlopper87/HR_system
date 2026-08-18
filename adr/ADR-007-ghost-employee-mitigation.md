# ADR-007: Ghost-employee mitigation (identity_verification, unplanned addition)

**Status:** Accepted (built Sprint 12c, 2026-08-13)
**Source:** originally recorded as a row in `Architecture-Design.md` §2 (kept there as the summary); this file is the
long-form record so `adr/` stays complete (H1 hardening, 2026-08-18).

## Context
Same reasoning as ADR-003 extended further: facial recognition has well-documented accuracy/bias limitations, and this system is Employment-Equity-focused, so an automated "this looks like a ghost employee" decision would be irresponsible without a human in the loop. No biometric vendor is under contract (mirrors A4's still-open assessment-provider shortlist), so face detection/descriptor extraction runs entirely in the browser (`@vladmandic/face-api`, TensorFlow.js) — the raw photo/video never reaches the server, only the derived 128-float descriptor. POPIA (s26/27) treats biometric data as "special personal information," gated by its own dedicated consent purpose, separate from this system's generic P/I/S/R tiers

## Decision
Client-side face descriptor matching (no 3rd-party biometric vendor), human-review-required for every non-match

## Consequences
See the corresponding entry in `Sprint-Plan-HCM-System.md` (implementation notes, design-tension callout, verification)
and the module rules in `hcm/README.md` for how the decision constrains later work.
