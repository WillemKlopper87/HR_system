"""Daily reminder sweep for the two fixed dates on the EE statutory
calendar that don't depend on any one employee's record (unlike
core_hr/contract_reminders.py, learning/reminders.py) -- both are
whole-employer deadlines, so there's one notification event per offset
per year, not one per row. Same exact-offset-day shape and same accepted
same-day-rerun risk as those two modules (design note in both:
core_hr/contract_reminders.py's docstring).

Two dates, deliberately not three: the certificate's 12-month expiry
(EEA15/16A-D) has no tracker yet -- there is no certificate model to read
an issue date from -- so it isn't reminded here; it belongs with that
model when it's built. WSP/ATR's 30 April SETA deadline is a learning-app
readiness check (training committee consultation + submission), not an
EE-reporting one, so it stays out of this module too.

"Last working day" is approximated as the last weekday (Mon-Fri) of the
month -- public holidays aren't accounted for, same precision level as a
calendar reminder needs, not a filing engine."""
from __future__ import annotations

import calendar
from datetime import date

from django.conf import settings
from django.utils import timezone

from notifications.services import employees_with_role, notify_many

from .models import EEReport


def _last_weekday_of_month(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    day = date(year, month, last_day)
    while day.weekday() >= 5:  # Saturday=5, Sunday=6
        day = day.replace(day=day.day - 1)
    return day


def _next_occurrence(today: date, month: int, day: int) -> date:
    candidate = date(today.year, month, day)
    return candidate if candidate >= today else date(today.year + 1, month, day)


def _next_last_weekday_of_month(today: date, month: int) -> date:
    candidate = _last_weekday_of_month(today.year, month)
    return candidate if candidate >= today else _last_weekday_of_month(today.year + 1, month)


def _ee_recipients():
    return (employees_with_role("hr_admin") | employees_with_role("ee_manager")).distinct()


def run_ee_statutory_reminders(*, dry_run: bool = False, today: date | None = None) -> dict:
    today = today or timezone.localdate()
    offsets = set(settings.EE_STATUTORY_REMINDER_OFFSETS_DAYS)

    online_report_deadline = _next_occurrence(today, 1, 15)
    eea14_deadline = _next_last_weekday_of_month(today, 8)

    online_report_reminders = 0
    eea14_reminders = 0

    if (online_report_deadline - today).days in offsets:
        report_year = online_report_deadline.year - 1
        outstanding = [
            form_type for form_type in (EEReport.FormType.EEA2, EEReport.FormType.EEA4)
            if not EEReport.objects.filter(
                form_type=form_type, report_year=report_year, status=EEReport.Status.SIGNED_OFF
            ).exists()
        ]
        if outstanding:
            recipients = list(_ee_recipients())
            if recipients:
                if not dry_run:
                    notify_many(
                        recipients, kind="ee_statutory_reminder",
                        title=f"EE report submission closes {online_report_deadline:%d %b %Y}",
                        body=(
                            f"Still outstanding for report year {report_year}: "
                            f"{', '.join(f.upper() for f in outstanding)}. Sign off at /ee-reporting."
                        ),
                        link="/ee-reporting",
                    )
                online_report_reminders += 1

    if (eea14_deadline - today).days in offsets:
        recipients = list(_ee_recipients())
        if recipients:
            if not dry_run:
                notify_many(
                    recipients, kind="ee_statutory_reminder",
                    title=f"EEA14 deadline {eea14_deadline:%d %b %Y} — notice of inability to report",
                    body=(
                        "If this year's EE report cannot be filed, written reasons and evidence must reach the "
                        "Director-General by this date (EE Regulations 2025, reg. 10)."
                    ),
                    link="/ee-reporting",
                )
            eea14_reminders += 1

    return {"online_report_reminders": online_report_reminders, "eea14_reminders": eea14_reminders}
