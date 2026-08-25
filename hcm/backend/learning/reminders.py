"""Daily reminder sweep for mandatory training (C6, design spec §2.9).
Mirrors core_hr/contract_reminders.py's exact-offset-day shape (not
performance/reminders.py's ReminderLog-deduped range shape) -- this
task's queries are narrow exact-day matches, run once daily via Celery
beat, so the only double-send risk is a manual same-day re-run --
accepted for the same reason contract_reminders.py's own docstring
accepts it: an extra in-app nudge, not a duplicate decision or data
change.

Two nudges, both reusing learning.compliance's own derivation (never
re-computed here):
* the employee is notified once, when their own due date is
  MANDATORY_TRAINING_REMINDER_OFFSET_DAYS away (a "due" status hitting
  the configured offset);
* their manager is notified once, the day a requirement actually lapses
  into overdue (an "overdue" status whose due date was exactly today) --
  a single event, not a repeated daily nag for the whole time someone
  stays overdue; the data-quality exception and dashboard already
  surface the ongoing state for anyone who checks.
"""
from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from core_hr.models import Employee
from notifications.services import notify

from .compliance import compliance_matrix


def run_mandatory_training_reminders(*, dry_run: bool = False) -> dict:
    today = timezone.localdate()
    offset_days = settings.MANDATORY_TRAINING_REMINDER_OFFSET_DAYS

    employees = {e.id: e for e in Employee.objects.select_related("user").all()}
    statuses = compliance_matrix(list(employees.values()), as_of=today)

    employee_reminders = 0
    manager_reminders = 0

    for status in statuses:
        employee = employees.get(status.employee_id)
        if employee is None:
            continue

        if status.status == "due" and (status.due_date - today).days == offset_days:
            if not dry_run:
                notify(
                    recipient=employee, kind="mandatory_training_reminder",
                    title=f"{status.course_name} is due {status.due_date:%d %b %Y}",
                    body="This course is mandatory for your role — please plan and complete it before the due date.",
                    link="/my-learning",
                )
            employee_reminders += 1

        elif status.status == "overdue" and (today - status.due_date).days == 0:
            version = employee.current_version
            manager = version.manager if version is not None else None
            if manager is not None:
                if not dry_run:
                    notify(
                        recipient=manager, kind="mandatory_training_reminder",
                        title=f"{employee.first_name} {employee.last_name} is overdue on {status.course_name}",
                        body=f"Was due {status.due_date:%d %b %Y}. Review at /team-development.",
                        link="/team-development",
                    )
                manager_reminders += 1

    return {"employee_reminders": employee_reminders, "manager_reminders": manager_reminders}
