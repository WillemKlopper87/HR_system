from __future__ import annotations

import uuid

from .base import AssessmentProviderAdapter, AssignOutcome, ResultOutcome


class SandboxAdapter(AssessmentProviderAdapter):
    """No real external provider is under contract — Sprint-0-Decision-
    Log.md action item A4 ("shortlist 1-2 assessment providers with
    documented APIs") was explicitly deferred to Sprint 12 planning and
    remains open. This adapter fulfils the exact same interface a real one
    would, entirely in-process, so the rest of the module — and its tests —
    exercise the real assign -> webhook -> result flow end-to-end. Swapping
    in a real provider later means adding one adapter class and flipping
    ProviderConfig.active, not touching services.py."""

    provider_key = "sandbox"

    def assign(self, assignment) -> AssignOutcome:
        reference = f"sandbox-{uuid.uuid4().hex[:12]}"
        return AssignOutcome(
            provider_reference=reference,
            access_url=f"https://sandbox-assessments.example/take/{reference}",
        )

    def status(self, assignment) -> str:
        return assignment.status

    def result(self, assignment) -> ResultOutcome:
        result = getattr(assignment, "result", None)
        if result is None:
            raise ValueError("No result recorded yet for this assignment.")
        return ResultOutcome(raw_score=result.raw_score, summary=result.summary, detail=result.detail)
