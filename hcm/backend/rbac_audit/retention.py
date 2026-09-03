"""Scheduled retention execution (Data-Dictionary.md `retention_rule`).

`RetentionRule` rows (Sprint 2) describe *what* to do per entity type;
this module is the executor that was deferred to hardening (H1). Two
design points worth knowing:

* **Handlers are registered by the app that owns the model**, from that
  app's `AppConfig.ready()`, via `register(entity_type, handler)`. The
  executor here never imports a peer app (README module rule), it only
  dispatches by `RetentionRule.entity_type` ("app_label.ModelName").
  A rule with no registered handler is reported as `no_handler`, never
  guessed at — generic "delete everything older than X" across arbitrary
  FKs is exactly the kind of thing that must not run unattended.
* Every real (non-dry-run) execution is audit-logged as one
  `AuditLogEntry` per rule (`DELETE` for delete rules, `UPDATE` for
  anonymise) with the affected count in `fields_touched`, actor=None
  (system), so the auditor role can see retention ran.

Handler contract::

    def handler(*, cutoff: datetime, action: str, dry_run: bool) -> int:
        '''Return the number of rows that were (or would be) affected.'''
"""
from __future__ import annotations

import calendar
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from django.utils import timezone

from .models import AuditLogEntry, RetentionRule, RetentionRuleRun, RetentionRun
from .tiers import FieldTier

logger = logging.getLogger(__name__)

Handler = Callable[..., int]
_HANDLERS: dict[str, Handler] = {}


def register(entity_type: str, handler: Handler) -> None:
    """Register (or replace) the handler for an `app_label.ModelName`."""
    _HANDLERS[entity_type] = handler


def unregister(entity_type: str) -> None:
    _HANDLERS.pop(entity_type, None)


def get_handler(entity_type: str) -> Handler | None:
    return _HANDLERS.get(entity_type)


def registered_entity_types() -> list[str]:
    return sorted(_HANDLERS)


@contextmanager
def temporary_handler(entity_type: str, handler: Handler):
    """Test helper: register for the duration of a `with` block, restoring
    whatever was there before."""
    previous = _HANDLERS.get(entity_type)
    _HANDLERS[entity_type] = handler
    try:
        yield
    finally:
        if previous is None:
            _HANDLERS.pop(entity_type, None)
        else:
            _HANDLERS[entity_type] = previous


def cutoff_for(now: datetime, period_months: int) -> datetime:
    """`now` minus a whole number of calendar months, clamping the day to
    the target month's length (31 Mar - 1 month = 28 Feb, not 3 Mar)."""
    month_index = now.year * 12 + (now.month - 1) - period_months
    year, month = divmod(month_index, 12)
    month += 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day)


@dataclass
class RetentionRunResult:
    entity_type: str
    action: str
    period_months: int
    cutoff: datetime | None
    status: str  # ok | skipped | no_handler | error
    affected: int = 0
    dry_run: bool = False
    detail: str = ""
    extra: dict = field(default_factory=dict)


def run_retention(*, dry_run: bool = False, now: datetime | None = None) -> list[RetentionRunResult]:
    """Execute every active, non-RETAIN rule through its registered handler.
    Failures are isolated per rule (one bad handler doesn't stop the run).

    HCM remediation M-2: also persists a RetentionRun + one RetentionRuleRun
    per rule, so a run's outcome — including `error` and `no_handler`,
    which previously existed only as a log line — has a durable, queryable
    record. The in-memory return value is unchanged; every existing caller
    keeps working exactly as before."""
    now = now or timezone.now()
    run = RetentionRun.objects.create(started_at=now, dry_run=dry_run)
    results: list[RetentionRunResult] = []
    for rule in RetentionRule.objects.all().order_by("entity_type"):
        base = dict(entity_type=rule.entity_type, action=rule.action, period_months=rule.period_months, dry_run=dry_run)
        if not rule.active or rule.action == RetentionRule.Action.RETAIN:
            results.append(RetentionRunResult(cutoff=None, status="skipped", detail="inactive or retain", **base))
            continue
        handler = get_handler(rule.entity_type)
        cutoff = cutoff_for(now, rule.period_months)
        if handler is None:
            logger.warning("retention: no handler registered for %s — skipped", rule.entity_type)
            results.append(RetentionRunResult(cutoff=cutoff, status="no_handler", **base))
            continue
        try:
            affected = int(handler(cutoff=cutoff, action=rule.action, dry_run=dry_run) or 0)
        except Exception as exc:  # noqa: BLE001 — isolate per rule, report, keep going
            logger.exception("retention: handler for %s failed", rule.entity_type)
            results.append(RetentionRunResult(cutoff=cutoff, status="error", detail=str(exc), **base))
            continue
        if not dry_run and affected:
            AuditLogEntry.objects.create(
                actor=None,
                action=(
                    AuditLogEntry.Action.DELETE
                    if rule.action == RetentionRule.Action.DELETE
                    else AuditLogEntry.Action.UPDATE
                ),
                entity_type=rule.entity_type,
                entity_id="",
                field_tier=FieldTier.INTERNAL,
                fields_touched=f"retention:{rule.action}:{affected} rows older than {cutoff.date().isoformat()}",
            )
        results.append(RetentionRunResult(cutoff=cutoff, status="ok", affected=affected, **base))

    RetentionRuleRun.objects.bulk_create([
        RetentionRuleRun(
            run=run, entity_type=r.entity_type, action=r.action, period_months=r.period_months,
            cutoff=r.cutoff, status=r.status, affected=r.affected, detail=r.detail,
        )
        for r in results
    ])
    run.completed_at = timezone.now()
    run.save(update_fields=["completed_at"])
    return results


# --- rbac_audit's own handlers ------------------------------------------------

def _audit_log_handler(*, cutoff, action, dry_run) -> int:
    """Audit entries are append-only by design; the only sanctioned
    retention action is DELETE after the statutory period (Data-Dictionary
    says >= 5 years). Anonymise makes no sense here and is a no-op."""
    if action != RetentionRule.Action.DELETE:
        return 0
    qs = AuditLogEntry.objects.filter(timestamp__lt=cutoff)
    if dry_run:
        return qs.count()
    deleted, _ = qs.delete()
    return deleted


def _step_up_grant_handler(*, cutoff, action, dry_run) -> int:
    from .models import StepUpGrant

    if action != RetentionRule.Action.DELETE:
        return 0
    qs = StepUpGrant.objects.filter(expires_at__lt=cutoff)
    if dry_run:
        return qs.count()
    deleted, _ = qs.delete()
    return deleted


def register_builtin_handlers() -> None:
    register("rbac_audit.AuditLogEntry", _audit_log_handler)
    register("rbac_audit.StepUpGrant", _step_up_grant_handler)
