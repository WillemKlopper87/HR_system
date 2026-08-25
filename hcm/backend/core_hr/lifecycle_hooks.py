"""Registry for the parts of hire()/exit-execution that live outside
core_hr (C1 part 3 slice 3 — onboarding/offboarding checklists, spec
docs/superpowers/specs/2026-08-24-onboarding-offboarding-checklists-design.md
§6). Same shape and same reasoning as `core_hr/access_cascade.py` and
`core_hr/data_quality.py`: `onboarding` is a domain app and core_hr is
SHARED_KERNEL and must not import it (rbac_audit/test_module_boundaries.py
enforces this mechanically), so a domain app registers a handler from its
own `AppConfig.ready()` and core_hr dispatches by name without ever
importing the app.

Two independent registries, not one, because the two triggers carry
different arguments (a hire handler only ever needs the new employee; an
exit-completion handler also needs the `EmploymentChange` that just
executed, e.g. so `onboarding` can record which exit created an
offboarding checklist).

Handler contract::

    def hire_handler(employee) -> int:
        '''Whatever this app wants to do when `employee` is hired. Return
        the number of rows created/affected (0 if nothing happened) --
        unused today but kept for parity with access_cascade.py's handlers
        and in case a future caller wants to log it.'''

    def exit_completion_handler(employee, change) -> int:
        '''Whatever this app wants to do once `change` (an EmploymentChange
        of an ENDING type) has finished executing -- i.e. employment is
        already closed by the time this runs. Same return contract.'''

Handler failure is isolated exactly like access_cascade.py's and
data_quality.py's: one failing handler must not abort a hire or an exit,
so a raised exception is caught, logged loudly, and the run continues."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Callable

logger = logging.getLogger(__name__)

HireHandler = Callable[..., int]
ExitCompletionHandler = Callable[..., int]
_HIRE_HANDLERS: dict[str, HireHandler] = {}
_EXIT_COMPLETION_HANDLERS: dict[str, ExitCompletionHandler] = {}


def register_hire_handler(name: str, handler: HireHandler) -> None:
    """Register (or replace) the hire handler for `name` (an
    "app_label.ModelName"-shaped key, matching access_cascade.py's
    convention -- used only as a label here, not resolved via the app
    registry)."""
    _HIRE_HANDLERS[name] = handler


def unregister_hire_handler(name: str) -> None:
    _HIRE_HANDLERS.pop(name, None)


def register_exit_completion_handler(name: str, handler: ExitCompletionHandler) -> None:
    _EXIT_COMPLETION_HANDLERS[name] = handler


def unregister_exit_completion_handler(name: str) -> None:
    _EXIT_COMPLETION_HANDLERS.pop(name, None)


def registered_hire_handlers() -> list[str]:
    return sorted(_HIRE_HANDLERS)


def registered_exit_completion_handlers() -> list[str]:
    return sorted(_EXIT_COMPLETION_HANDLERS)


@contextmanager
def temporary_hire_handler(name: str, handler: HireHandler):
    """Test helper: register for the duration of a `with` block, restoring
    whatever was there before (mirrors access_cascade.py's
    temporary_exit_handler)."""
    previous = _HIRE_HANDLERS.get(name)
    _HIRE_HANDLERS[name] = handler
    try:
        yield
    finally:
        if previous is None:
            _HIRE_HANDLERS.pop(name, None)
        else:
            _HIRE_HANDLERS[name] = previous


@contextmanager
def temporary_exit_completion_handler(name: str, handler: ExitCompletionHandler):
    previous = _EXIT_COMPLETION_HANDLERS.get(name)
    _EXIT_COMPLETION_HANDLERS[name] = handler
    try:
        yield
    finally:
        if previous is None:
            _EXIT_COMPLETION_HANDLERS.pop(name, None)
        else:
            _EXIT_COMPLETION_HANDLERS[name] = previous


def run_hire_handlers(employee) -> dict[str, int]:
    """Run every registered hire handler for `employee`. Returns
    {name: affected_count} for handlers that completed (a handler that
    raised is simply absent from the result -- the exception is already
    logged loudly here, matching access_cascade.py's run_exit_handlers)."""
    results: dict[str, int] = {}
    for name, handler in _HIRE_HANDLERS.items():
        try:
            results[name] = int(handler(employee) or 0)
        except Exception:  # noqa: BLE001 -- isolate per handler, keep going
            logger.exception("lifecycle_hooks: hire handler %s failed for employee %s", name, employee.employee_number)
    return results


def run_exit_completion_handlers(employee, change) -> dict[str, int]:
    results: dict[str, int] = {}
    for name, handler in _EXIT_COMPLETION_HANDLERS.items():
        try:
            results[name] = int(handler(employee, change) or 0)
        except Exception:  # noqa: BLE001 -- isolate per handler, keep going
            logger.exception(
                "lifecycle_hooks: exit-completion handler %s failed for employee %s (change #%s)",
                name, employee.employee_number, change.pk,
            )
    return results
