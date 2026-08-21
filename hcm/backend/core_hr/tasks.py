"""Celery tasks for core_hr (C1 part 2, extended by C1 part 3). Scheduled
by CELERY_BEAT_SCHEDULE (config/settings.py)."""
from celery import shared_task

from .contract_reminders import run_contract_reminders
from .exits import execute_due_employment_changes


@shared_task(name="core_hr.tasks.run_contract_reminders_task")
def run_contract_reminders_task(dry_run: bool = False) -> dict:
    """The one daily core_hr beat job. C1 part 3 (design spec §2.3) rides
    this existing job for the employment-exit cascade's scheduled half
    rather than adding a second CELERY_BEAT_SCHEDULE entry: every CONFIRMED
    EmploymentChange whose effective_date has arrived executes here,
    alongside the contract-expiry reminder sweep it already ran.
    `dry_run` is a "don't actually do anything today" flag for the whole
    task, not just the reminder half -- executing exits during a
    reminder-only dry run would be a surprising side effect."""
    result = run_contract_reminders(dry_run=dry_run)
    if not dry_run:
        result["employment_changes"] = execute_due_employment_changes()
    return result
