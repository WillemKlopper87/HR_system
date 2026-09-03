"""Registry for the parts of the employment-exit access cascade (C1 part 3)
that live outside core_hr. `core_hr/exits.py` handles what it owns
directly -- RoleAssignment revocation/restoration and disabling/enabling
`Employee.user` -- but suspending a departed or suspended person's
biometric enrolment means touching `identity_verification.BiometricEnrollment`,
and `identity_verification` is a domain app: core_hr is SHARED_KERNEL and
must not import it (rbac_audit/test_module_boundaries.py enforces this
mechanically). This is the same registry shape already proved out in
`core_hr/data_quality.py` (itself mirroring `rbac_audit/retention.py`):
a domain app registers a handler from its own `AppConfig.ready()`;
core_hr dispatches by name without ever importing the app.

Handler contract::

    def exit_handler(employee) -> int:
        '''Suspend whatever this app owns for `employee`. Return the number
        of rows affected (0 if there was nothing to do) -- the cascade uses
        this to decide whether an audit-log entry is worth writing.'''

    def restore_handler(employee) -> int:
        '''The inverse, run on LIFT_SUSPENSION execution. Same return
        contract.'''

Handler failure is isolated exactly like data_quality.py's: one failing
handler must not abort the exit or block its siblings (spec §6.4), so a
raised exception is caught, logged loudly, and the run continues. A
handler that fails contributes 0 to its own result and every other
handler still runs."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Callable

logger = logging.getLogger(__name__)

Handler = Callable[..., int]
_EXIT_HANDLERS: dict[str, Handler] = {}
_RESTORE_HANDLERS: dict[str, Handler] = {}


def register_exit_handler(name: str, handler: Handler) -> None:
    """Register (or replace) the exit-suspension handler for `name` (an
    "app_label.ModelName"-shaped key, matching data_quality.py/retention.py's
    convention -- used only as a label here, not resolved via the app
    registry)."""
    _EXIT_HANDLERS[name] = handler


def unregister_exit_handler(name: str) -> None:
    _EXIT_HANDLERS.pop(name, None)


def register_restore_handler(name: str, handler: Handler) -> None:
    _RESTORE_HANDLERS[name] = handler


def unregister_restore_handler(name: str) -> None:
    _RESTORE_HANDLERS.pop(name, None)


def registered_exit_handlers() -> list[str]:
    return sorted(_EXIT_HANDLERS)


def registered_restore_handlers() -> list[str]:
    return sorted(_RESTORE_HANDLERS)


@contextmanager
def temporary_exit_handler(name: str, handler: Handler):
    """Test helper: register for the duration of a `with` block, restoring
    whatever was there before (mirrors data_quality.py's temporary_handler)."""
    previous = _EXIT_HANDLERS.get(name)
    _EXIT_HANDLERS[name] = handler
    try:
        yield
    finally:
        if previous is None:
            _EXIT_HANDLERS.pop(name, None)
        else:
            _EXIT_HANDLERS[name] = previous


@contextmanager
def temporary_restore_handler(name: str, handler: Handler):
    previous = _RESTORE_HANDLERS.get(name)
    _RESTORE_HANDLERS[name] = handler
    try:
        yield
    finally:
        if previous is None:
            _RESTORE_HANDLERS.pop(name, None)
        else:
            _RESTORE_HANDLERS[name] = previous


def _run(handlers: dict[str, Handler], employee, *, only: set[str] | None = None) -> dict[str, int]:
    results: dict[str, int] = {}
    for name, handler in handlers.items():
        if only is not None and name not in only:
            continue
        try:
            results[name] = int(handler(employee) or 0)
        except Exception:  # noqa: BLE001 -- isolate per handler, keep going
            logger.exception(
                "access_cascade: handler for %s failed for employee %s",
                name, employee.employee_number,
            )
    return results


def run_exit_handlers(employee, *, only: set[str] | None = None) -> dict[str, int]:
    """Run registered exit handlers for `employee`. Returns
    {name: affected_count} for handlers that completed (a handler that
    raised is simply absent from the result, not included with 0 -- the
    caller can't tell "nothing to do" from "it blew up" otherwise, and the
    exception is already logged loudly here). `only`, when given, restricts
    execution to that subset of registered names -- used by HCM remediation
    H-2's retry_access_revocation() to re-run just the domains a prior
    AccessRevocationObligation recorded as FAILED, not every registered
    domain again. `only=None` (the default) runs every registered handler,
    unchanged from the original behaviour."""
    return _run(_EXIT_HANDLERS, employee, only=only)


def run_restore_handlers(employee, *, only: set[str] | None = None) -> dict[str, int]:
    """Run registered restore handlers for `employee`. `only`, when given,
    restricts execution to that subset of registered names (HCM
    remediation H-1) -- a lift must restore a cascade domain only when the
    matching suspension's own withdrawal actually affected it, not every
    domain that happens to be inactive right now for some other reason.
    `only=None` (the default) runs every registered handler, unchanged
    from the original behaviour."""
    return _run(_RESTORE_HANDLERS, employee, only=only)
