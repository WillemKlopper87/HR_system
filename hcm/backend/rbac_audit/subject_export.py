"""HCM remediation H-3: registry for the personal-data domains a POPIA
subject-data export must cover. Same shape as retention.py and
core_hr/access_cascade.py on purpose (register from the owning app's
AppConfig.ready(), dispatch by name, this module never imports a peer
app) -- the third instance of the same registry pattern in this codebase.

Before this registry, documents/services.py::_serialise_for_export
covered exactly the fields it happened to know about (core employee
fields, documents, dependants, emergency contacts, consent records) and
complete_export_request() marked the request COMPLETED unconditionally --
so a subject whose personal data also lives in compensation, learning,
performance, etc. got an export that looked complete but wasn't, with
nothing recording that gap. Each registered domain now reports an
explicit outcome (never silence), and complete_export_request() checks
whether every REQUIRED domain actually succeeded before calling the
request COMPLETED.

Handler contract::

    def handler(employee) -> DomainExportResult:
        '''Return this domain's personal data for `employee`, or an
        explicit non-inclusion reason (NO_RECORDS/RETAINED/EXCLUDED).
        Raising is caught here and recorded as FAILED -- a handler must
        never be able to crash the overall export.'''
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


class DomainStatus:
    INCLUDED = "included"
    NO_RECORDS = "no_records"
    RETAINED = "retained"
    EXCLUDED = "excluded"
    FAILED = "failed"


@dataclass
class DomainExportResult:
    status: str
    record_count: int = 0
    payload: object = None
    detail: str = ""


Handler = Callable[..., DomainExportResult]
_HANDLERS: dict[str, Handler] = {}
_REQUIRED: set[str] = set()


def register(domain: str, handler: Handler, *, required: bool = True) -> None:
    """Register (or replace) the export handler for `domain`
    ("app_label.Label", matching retention.py/access_cascade.py's naming
    convention). `required` (default True) controls whether this domain
    FAILING blocks the overall request from being marked COMPLETED."""
    _HANDLERS[domain] = handler
    if required:
        _REQUIRED.add(domain)
    else:
        _REQUIRED.discard(domain)


def unregister(domain: str) -> None:
    _HANDLERS.pop(domain, None)
    _REQUIRED.discard(domain)


def registered_domains() -> list[str]:
    return sorted(_HANDLERS)


def required_domains() -> list[str]:
    return sorted(_REQUIRED)


@contextmanager
def temporary_handler(domain: str, handler: Handler, *, required: bool = True):
    """Test helper: register for the duration of a `with` block, restoring
    whatever was there before (mirrors retention.py's temporary_handler)."""
    had_previous = domain in _HANDLERS
    previous_handler = _HANDLERS.get(domain)
    previous_required = domain in _REQUIRED
    register(domain, handler, required=required)
    try:
        yield
    finally:
        if not had_previous:
            unregister(domain)
        else:
            register(domain, previous_handler, required=previous_required)


@dataclass
class SubjectExportManifest:
    domains: dict[str, DomainExportResult] = field(default_factory=dict)
    # Snapshotted from the registry at run_subject_export() time, not
    # read live from _REQUIRED by `complete` below -- a domain can be
    # unregistered (temporary_handler's cleanup, or a future
    # re-registration) after the run completes, which must not silently
    # change what an already-generated manifest reports as complete.
    required: frozenset[str] = field(default_factory=frozenset)

    @property
    def complete(self) -> bool:
        """False if any domain required AT RUN TIME FAILED (spec H-3: a
        request "cannot be marked complete merely because one owning app
        finished its portion"). A domain with no registered handler at
        all doesn't appear in `domains` and can't fail this check --
        missing coverage is a backlog item, not a per-request failure."""
        return not any(
            result.status == DomainStatus.FAILED
            for domain, result in self.domains.items()
            if domain in self.required
        )

    def as_dict(self) -> dict:
        return {
            domain: {"status": result.status, "record_count": result.record_count, "detail": result.detail}
            for domain, result in self.domains.items()
        }


def run_subject_export(employee) -> tuple[dict, SubjectExportManifest]:
    """Run every registered domain exporter for `employee`. Returns
    (payload, manifest): `payload` is {domain: result.payload} for
    domains with status INCLUDED; `manifest` records every registered
    domain's outcome (including NO_RECORDS/RETAINED/EXCLUDED/FAILED), so
    a completed export's silence on a domain is provably deliberate."""
    manifest = SubjectExportManifest(required=frozenset(_REQUIRED))
    payload: dict = {}
    for domain, handler in _HANDLERS.items():
        try:
            result = handler(employee)
        except Exception as exc:  # noqa: BLE001 -- isolate per domain, keep going
            logger.exception(
                "subject_export: handler for %s failed for employee %s", domain, employee.employee_number
            )
            result = DomainExportResult(status=DomainStatus.FAILED, detail=str(exc))
        manifest.domains[domain] = result
        if result.status == DomainStatus.INCLUDED:
            payload[domain] = result.payload
    return payload, manifest
