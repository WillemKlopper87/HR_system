# ADR-008: Policy document Q&A (policies app, unplanned addition)

**Status:** Accepted for the seam; chatbot/embeddings/LLM deferred (2026-08-13)
**Source:** originally recorded as a row in `Architecture-Design.md` §2 (kept there as the summary); this file is the
long-form record so `adr/` stays complete (H1 hardening, 2026-08-18).

## Context
Requested mid-build, scoped deliberately in phases (same "build the seam, defer the vendor" reasoning as ADR-003/ADR-007): no LLM API integration exists anywhere in this codebase yet, and wiring one is a real per-query cost + vendor decision that needs explicit sign-off, not something to bolt on incidentally. The specific risk that must be designed for before any chatbot ships: a user asking it how to circumvent, bypass, or find loopholes in a policy — retrieval-augmented answers must stay strictly grounded in the policy's own chunked text (never general knowledge), refuse circumvention-framed questions, and log every Q&A turn for HR audit, mirroring ADR-007's "no automated adverse action without a human" posture applied to advice instead of enrollment decisions. See the Policy section's entry in `Sprint-Plan-HCM-System.md` for the full phased plan

## Decision
Build the retrieval seam now (upload → text extraction → deterministic chunking), defer embeddings/vector search and the chatbot itself until an LLM vendor/model is explicitly chosen and an abuse-prevention design is signed off

## Consequences
See the corresponding entry in `Sprint-Plan-HCM-System.md` (implementation notes, design-tension callout, verification)
and the module rules in `hcm/README.md` for how the decision constrains later work.
