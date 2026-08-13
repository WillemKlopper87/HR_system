from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AssignOutcome:
    provider_reference: str
    access_url: str


@dataclass
class ResultOutcome:
    raw_score: str
    summary: str
    detail: dict


class AssessmentProviderAdapter(ABC):
    """Architecture-Design.md §11: "Adapter interface (assign, status,
    result) + inbound signed webhook; provider-specific adapter behind
    it. Sprint 12 acceptance criterion 'swap by reconfiguration' holds
    only if module code never imports a concrete adapter" — callers
    resolve an adapter through registry.get_active_adapter(), never by
    importing SandboxAdapter (or any future real-provider adapter)
    directly."""

    provider_key: str

    @abstractmethod
    def assign(self, assignment) -> AssignOutcome:
        """Create the assessment on the provider's side; return the
        opaque reference plus the URL the subject visits to take it."""

    @abstractmethod
    def status(self, assignment) -> str:
        """Poll the provider for current status — a fallback/
        reconciliation path; the primary completion signal is the inbound
        webhook (see services.py::process_webhook_result)."""

    @abstractmethod
    def result(self, assignment) -> ResultOutcome:
        """Fetch the final result once the provider reports completion."""
