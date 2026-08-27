"""Celery tasks for ee_reporting. Scheduled by CELERY_BEAT_SCHEDULE
(config/settings.py)."""
from celery import shared_task

from .reminders import run_ee_statutory_reminders


@shared_task(name="ee_reporting.tasks.run_ee_statutory_reminders_task")
def run_ee_statutory_reminders_task(dry_run: bool = False) -> dict:
    return run_ee_statutory_reminders(dry_run=dry_run)
