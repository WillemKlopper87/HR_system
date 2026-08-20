"""Celery tasks for core_hr (C1 part 2). Scheduled by CELERY_BEAT_SCHEDULE
(config/settings.py)."""
from celery import shared_task

from .contract_reminders import run_contract_reminders


@shared_task(name="core_hr.tasks.run_contract_reminders_task")
def run_contract_reminders_task(dry_run: bool = False) -> dict:
    return run_contract_reminders(dry_run=dry_run)
