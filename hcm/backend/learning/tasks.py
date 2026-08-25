"""Celery tasks for learning (C6). Scheduled by CELERY_BEAT_SCHEDULE
(config/settings.py)."""
from celery import shared_task

from .reminders import run_mandatory_training_reminders


@shared_task(name="learning.tasks.run_mandatory_training_reminders_task")
def run_mandatory_training_reminders_task(dry_run: bool = False) -> dict:
    return run_mandatory_training_reminders(dry_run=dry_run)
