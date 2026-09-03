"""Celery tasks owned by rbac_audit. Scheduled by CELERY_BEAT_SCHEDULE
(config/settings.py); runnable by hand via `manage.py run_retention`."""
from celery import shared_task

from . import retention


@shared_task(name="rbac_audit.tasks.run_retention_task")
def run_retention_task(dry_run: bool = False) -> dict:
    """HCM remediation M-2: `errors`/`no_handler` surface in the task's own
    result (visible in Celery's result backend/Flower) -- before this, a
    rule that errored or had no registered handler contributed nothing to
    the summary, so a scheduled run could look clean while quietly skipping
    or failing a rule. The full per-rule outcome is also now durably
    recorded by run_retention() itself (rbac_audit.RetentionRun /
    RetentionRuleRun), which is the authoritative record; this dict is
    just a same-run-at-a-glance summary."""
    results = retention.run_retention(dry_run=dry_run)
    return {
        "rules": len(results),
        "affected": sum(r.affected for r in results if r.status == "ok"),
        "errors": [r.entity_type for r in results if r.status == "error"],
        "no_handler": [r.entity_type for r in results if r.status == "no_handler"],
    }
