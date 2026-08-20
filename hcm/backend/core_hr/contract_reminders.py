"""Daily reminder sweep for fixed-term contracts approaching expiry (C1
part 2). Mirrors performance/reminders.py's shape, minus that module's
ReminderLog-based dedup: this task's query is a narrow exact-offset-day
match (not a range) and fires via Celery beat once daily, so the only
double-send risk is a manual re-run on the same day -- accepted as a
minor, non-critical-path simplification (an extra in-app nudge, not a
duplicate decision or data change) rather than building PC-1-scale
tracking infrastructure for a single-recipient-per-event feature. See
design spec §5."""
from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from notifications.services import employees_with_role, notify, notify_many

from .models import ContractRenewalDecision, EmployeeVersion


def run_contract_reminders(*, dry_run: bool = False) -> dict:
    today = timezone.localdate()
    offsets = set(settings.CONTRACT_REMINDER_OFFSETS_DAYS)
    escalation_days = settings.CONTRACT_ESCALATION_DAYS

    manager_reminders = 0
    hr_admin_versions = []  # [(version, employee_name, reason), ...]

    versions = EmployeeVersion.objects.current().filter(
        employment_status=EmployeeVersion.EmploymentStatus.FIXED_TERM,
        contract_end_date__isnull=False,
    ).select_related("employee", "manager")

    for version in versions:
        days_remaining = (version.contract_end_date - today).days
        if days_remaining not in offsets:
            continue

        decision = getattr(version, "contract_renewal_decision", None)
        if decision is not None and decision.status == ContractRenewalDecision.Status.DECIDED:
            continue

        employee_name = f"{version.employee.first_name} {version.employee.last_name}"

        if decision is None:
            if version.manager is not None:
                if not dry_run:
                    notify(
                        recipient=version.manager, kind="contract_reminder",
                        title=f"{employee_name}'s fixed-term contract ends {version.contract_end_date:%d %b %Y}",
                        body="Recommend renew, convert to permanent, or let lapse.",
                        link="/contract-renewals",
                    )
                manager_reminders += 1
            if days_remaining <= escalation_days:
                hr_admin_versions.append((version, employee_name, "no recommendation yet"))
        else:  # RECOMMENDED
            hr_admin_versions.append((version, employee_name, "awaiting your decision"))

    hr_admin_reminders = 0
    if hr_admin_versions:
        hr_admins = list(employees_with_role("hr_admin"))
        for version, employee_name, reason in hr_admin_versions:
            if hr_admins and not dry_run:
                notify_many(
                    hr_admins, kind="contract_reminder",
                    title=f"{employee_name}'s fixed-term contract ends {version.contract_end_date:%d %b %Y} ({reason})",
                    body="Review at /contract-renewals.",
                    link="/contract-renewals",
                )
            hr_admin_reminders += 1

    return {"manager_reminders": manager_reminders, "hr_admin_reminders": hr_admin_reminders}
