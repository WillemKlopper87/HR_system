"""Celery tasks for the performance module (PC-1, ADR-011).

`run_performance_reminders_task` is the daily beat job: it works out which
reminder offset falls today for whichever phase is open and pushes the
outstanding to-dos/digests/announcements. Safe to run twice — every emission
is keyed in `ReminderLog`.
"""
from celery import shared_task

from .reminders import run_reminders


@shared_task(name="performance.tasks.run_performance_reminders_task")
def run_performance_reminders_task(dry_run: bool = False) -> dict:
    return run_reminders(dry_run=dry_run).as_dict()
