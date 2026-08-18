"""Celery tasks owned by rbac_audit. Scheduled by CELERY_BEAT_SCHEDULE
(config/settings.py); runnable by hand via `manage.py run_retention`."""
from celery import shared_task

from . import retention


@shared_task(name="rbac_audit.tasks.run_retention_task")
def run_retention_task(dry_run: bool = False) -> dict:
    results = retention.run_retention(dry_run=dry_run)
    return {"rules": len(results), "affected": sum(r.affected for r in results if r.status == "ok")}
