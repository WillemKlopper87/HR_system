"""Celery entry points for the collab integration (ADR-011)."""
from celery import shared_task
from config.operational_metrics import record_integration

from . import collab
from .sync import sync_collab_ids


@shared_task(name="integrations.tasks.sync_collab_ids_task")
def sync_collab_ids_task(dry_run: bool = False) -> dict:
    record_integration("collab", "attempt")
    try:
        client = collab.get_client()
        if client is None:
            record_integration("collab", "skipped")
            return {"skipped": "collab integration disabled"}
        try:
            result = sync_collab_ids(client, dry_run=dry_run)
        finally:
            client.close()
    except Exception:
        record_integration("collab", "failure")
        raise
    record_integration("collab", "success")
    return {
        "employees_matched": result.employees_matched,
        "employees_unmatched": len(result.employees_unmatched),
        "departments_matched": result.departments_matched,
        "departments_unmatched": len(result.departments_unmatched),
        "dry_run": dry_run,
    }
