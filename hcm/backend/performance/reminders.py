"""Scheduled reminders for performance contracting (PC-1, ADR-011).

The user's own words for why this exists: KPIs get forgotten until it is a
last-minute rush, corporate reminder emails are ad hoc, and "the system could
notify/push them and remind them in advance to start preparing". So the
reminder schedule is part of the *period*, not an afterthought:

    phase.reminder_offsets_days = [28, 14, 7, 1]   # days before due_on
    phase.overdue_every_days    = 7                # after due_on, repeat

Each run (daily, Celery beat) computes who is still outstanding for the open
phase and emits, through `integrations.collab`:

  * one **work item per employee** — upserted by external ref
    `hcm:agreement:{id}:{stage}` so re-running never duplicates it, priority
    rising as the deadline approaches, deep-linked back into the HCM;
  * one **digest work item per Head** — "N of your team are outstanding";
  * a **critical announcement** per department when the phase opens, and again
    when it first goes overdue.

Idempotency is a `ReminderLog` row per (period, stage, kind, subject, offset).
Nothing here blocks the HCM: if collab is off or unreachable, the run records
what it could not send and returns; contracting still opens.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

from integrations import collab
from integrations.collab import CollabError
from notifications.services import notify

from .models import PerformanceAgreement, PerformancePeriod, PeriodPhase, ReminderLog

logger = logging.getLogger(__name__)

# Priority ladder as the deadline approaches (days remaining -> collab priority)
PRIORITY_LADDER = ((1, "urgent"), (7, "high"), (14, "normal"))
OVERDUE_PRIORITY = "urgent"

STAGE_TITLES = {
    PeriodPhase.Stage.CONTRACTING: "Complete and sign your {period} performance agreement",
    PeriodPhase.Stage.MIDYEAR: "Complete your {period} mid-year (Q2) performance review",
    PeriodPhase.Stage.FINAL: "Complete your {period} final (Q4) performance assessment",
}
# Which agreement statuses mean "this person is finished with this stage".
STAGE_DONE_STATUSES = {
    PeriodPhase.Stage.CONTRACTING: set(PerformanceAgreement.CONTRACTED_STATUSES),
    PeriodPhase.Stage.MIDYEAR: {
        PerformanceAgreement.Status.MIDYEAR_SIGNED, PerformanceAgreement.Status.FINAL_OPEN,
        PerformanceAgreement.Status.FINAL_EMPLOYEE_SIGNED, PerformanceAgreement.Status.FINAL_SIGNED,
        PerformanceAgreement.Status.ARCHIVED,
    },
    PeriodPhase.Stage.FINAL: {PerformanceAgreement.Status.FINAL_SIGNED, PerformanceAgreement.Status.ARCHIVED},
}


@dataclass
class ReminderRun:
    period: str = ""
    stage: str = ""
    days_to_due: int | None = None
    offset: int | None = None
    outstanding: int = 0
    items_sent: int = 0
    digests_sent: int = 0
    announcements_sent: int = 0
    skipped_no_collab_account: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "period": self.period, "stage": self.stage, "days_to_due": self.days_to_due, "offset": self.offset,
            "outstanding": self.outstanding, "items_sent": self.items_sent, "digests_sent": self.digests_sent,
            "announcements_sent": self.announcements_sent,
            "skipped_no_collab_account": len(self.skipped_no_collab_account),
            "errors": self.errors, "dry_run": self.dry_run, "note": self.note,
        }


def due_offset(phase: PeriodPhase, today: date) -> int | None:
    """Which configured reminder fires today: a positive offset for
    'N days before due', a negative one for an overdue repeat, else None."""
    days_left = (phase.due_on - today).days
    if days_left >= 0:
        return days_left if days_left in set(phase.reminder_offsets_days or []) else None
    overdue_days = -days_left
    every = phase.overdue_every_days or 0
    if every and overdue_days % every == 0:
        return -overdue_days
    return None


def priority_for(days_left: int | None) -> str:
    if days_left is None or days_left < 0:
        return OVERDUE_PRIORITY
    for threshold, priority in PRIORITY_LADDER:
        if days_left <= threshold:
            return priority
    return "low"


def outstanding_agreements(period: PerformancePeriod, stage: str):
    done = STAGE_DONE_STATUSES.get(stage, set())
    return (
        period.agreements.exclude(status__in=done)
        .exclude(status=PerformanceAgreement.Status.ARCHIVED)
        .select_related("employee", "head")
    )


def open_phase_for(period: PerformancePeriod) -> PeriodPhase | None:
    stage = {
        PerformancePeriod.Status.CONTRACTING: PeriodPhase.Stage.CONTRACTING,
        PerformancePeriod.Status.MIDYEAR: PeriodPhase.Stage.MIDYEAR,
        PerformancePeriod.Status.FINAL: PeriodPhase.Stage.FINAL,
    }.get(period.status)
    return period.phase(stage) if stage else None


def deep_link(agreement: PerformanceAgreement) -> str:
    base = getattr(settings, "HCM_PUBLIC_URL", "").rstrip("/")
    return f"{base}/my-performance/agreements/{agreement.pk}"


def _already_sent(key: str) -> bool:
    return ReminderLog.objects.filter(key=key).exists()


def _record(period, stage, kind, key, **kw) -> bool:
    """Write the log row; a unique-key clash means a concurrent run already
    sent it, which is a success, not an error."""
    try:
        ReminderLog.objects.create(period=period, stage=stage, kind=kind, key=key, **kw)
        return True
    except IntegrityError:
        return False


def run_reminders(*, period: PerformancePeriod | None = None, today: date | None = None, dry_run: bool = False,
                  force_offset: int | None = None) -> ReminderRun:
    today = today or timezone.localdate()
    run = ReminderRun(dry_run=dry_run)

    if period is None:
        period = (
            PerformancePeriod.objects.filter(
                status__in=[
                    PerformancePeriod.Status.CONTRACTING,
                    PerformancePeriod.Status.MIDYEAR,
                    PerformancePeriod.Status.FINAL,
                ]
            )
            .order_by("-start_date")
            .first()
        )
    if period is None:
        run.note = "No period has an open phase — nothing to remind about."
        return run

    phase = open_phase_for(period)
    if phase is None:
        run.note = f"Period {period.name} has no phase configured for status {period.status}."
        return run

    run.period, run.stage = period.name, phase.stage
    run.days_to_due = (phase.due_on - today).days
    offset = force_offset if force_offset is not None else due_offset(phase, today)
    if offset is None:
        run.note = "No reminder offset falls on today."
        return run
    run.offset = offset

    agreements = list(outstanding_agreements(period, phase.stage))
    run.outstanding = len(agreements)
    if not agreements:
        run.note = "Nobody is outstanding — no reminders needed."
        return run

    client = None if dry_run else collab.get_client()
    if client is None and not dry_run:
        run.note = "Collab integration is off — reminders computed but not delivered."

    label = f"T-{offset}" if offset >= 0 else f"overdue+{-offset}"
    title_template = STAGE_TITLES.get(phase.stage, "Complete your {period} performance step")
    project_cache: dict[str, str] = {}

    try:
        for agreement in agreements:
            employee = agreement.employee
            key = f"{period.name}:{phase.stage}:employee_item:{employee.employee_number}:{label}"

            # In-app is a second, independent channel from the collab push
            # below -- it needs no collab_user_id/department mapping, so it
            # fires for every outstanding employee, not just the ones collab
            # can reach. Own idempotency key (same `key`, different channel)
            # so a rerun never double-notifies either channel.
            in_app_key = f"{key}:in_app"
            if not dry_run and not _already_sent(in_app_key):
                notify(
                    recipient=employee, kind="pc_reminder",
                    title=title_template.format(period=period.name),
                    body=f"Due {phase.due_on:%d %b %Y}.",
                    link="/my-performance",
                )
                _record(period, phase.stage, ReminderLog.Kind.EMPLOYEE_ITEM, in_app_key, employee=employee,
                        agreement=agreement, offset_days=offset, channel="in_app")

            if _already_sent(key):
                continue
            if not employee.collab_user_id:
                run.skipped_no_collab_account.append(employee.employee_number)
                # Still log it, so the gap is visible in reporting rather than silent.
                if not dry_run:
                    _record(period, phase.stage, ReminderLog.Kind.EMPLOYEE_ITEM, key, employee=employee,
                            agreement=agreement, offset_days=offset, channel="none",
                            detail="no collab account for this employee")
                continue
            if client is None:
                # dry-run previews what would go out; "collab off" delivers
                # nothing, so it must not claim it did.
                if dry_run:
                    run.items_sent += 1
                continue

            version = employee.current_version
            department = version.department if version else None
            collab_department = getattr(department, "collab_department_id", "") or ""
            if not collab_department:
                run.skipped_no_collab_account.append(f"{employee.employee_number} (department unmapped)")
                _record(period, phase.stage, ReminderLog.Kind.EMPLOYEE_ITEM, key, employee=employee,
                        agreement=agreement, offset_days=offset, channel="none",
                        detail="department not mapped to collab")
                continue
            project_name = f"Performance {period.name}"
            if collab_department not in project_cache:
                project_cache[collab_department] = client.ensure_project(
                    collab_department_id=collab_department,
                    name=project_name,
                    description=f"Performance contracting and reviews for {period.name} (pushed by the HCM).",
                )
            external_ref = f"hcm:agreement:{agreement.pk}:{phase.stage}"
            body = (
                f"{title_template.format(period=period.name)} — due {phase.due_on:%d %b %Y}.\n"
                f"Open it here: {deep_link(agreement)}"
            )
            client.upsert_work_item(
                external_ref,
                project_id=project_cache[collab_department],
                title=title_template.format(period=period.name),
                description=body,
                assignee_user_id=employee.collab_user_id,
                due_on=phase.due_on,
                priority=priority_for(offset if offset >= 0 else None),
            )
            run.items_sent += 1
            _record(period, phase.stage, ReminderLog.Kind.EMPLOYEE_ITEM, key, employee=employee,
                    agreement=agreement, offset_days=offset, external_ref=external_ref)

        # Head digests — one per Head with outstanding reports.
        by_head: dict[int, list[PerformanceAgreement]] = {}
        for agreement in agreements:
            if agreement.head_id:
                by_head.setdefault(agreement.head_id, []).append(agreement)
        for head_id, items in by_head.items():
            head = items[0].head
            key = f"{period.name}:{phase.stage}:head_digest:{head.employee_number}:{label}"

            in_app_key = f"{key}:in_app"
            if not dry_run and not _already_sent(in_app_key):
                notify(
                    recipient=head, kind="pc_reminder",
                    title=f"{len(items)} of your team still to complete {period.name} {phase.get_stage_display()}",
                    body=", ".join(f"{a.employee.first_name} {a.employee.last_name}" for a in items[:20]),
                    link="/team-performance",
                )
                _record(period, phase.stage, ReminderLog.Kind.HEAD_DIGEST, in_app_key, employee=head,
                        offset_days=offset, channel="in_app")

            if _already_sent(key):
                continue
            if not head.collab_user_id:
                continue
            if client is None:
                if dry_run:
                    run.digests_sent += 1
                continue
            version = head.current_version
            collab_department = getattr(getattr(version, "department", None), "collab_department_id", "") or ""
            if not collab_department:
                continue
            if collab_department not in project_cache:
                project_cache[collab_department] = client.ensure_project(
                    collab_department_id=collab_department, name=f"Performance {period.name}"
                )
            external_ref = f"hcm:head-digest:{head.pk}:{period.pk}:{phase.stage}"
            client.upsert_work_item(
                external_ref,
                project_id=project_cache[collab_department],
                title=f"{len(items)} of your team still to complete {period.name} {phase.get_stage_display()}",
                description=(
                    "Outstanding: "
                    + ", ".join(f"{a.employee.first_name} {a.employee.last_name}" for a in items[:20])
                    + (f" and {len(items) - 20} more" if len(items) > 20 else "")
                    + f"\nDue {phase.due_on:%d %b %Y}."
                ),
                assignee_user_id=head.collab_user_id,
                due_on=phase.due_on,
                priority=priority_for(offset if offset >= 0 else None),
            )
            run.digests_sent += 1
            _record(period, phase.stage, ReminderLog.Kind.HEAD_DIGEST, key, employee=head,
                    offset_days=offset, external_ref=external_ref)

        # Critical announcement at phase open (T- the largest offset) and first overdue day.
        largest_offset = max(phase.reminder_offsets_days or [0]) if phase.reminder_offsets_days else 0
        announce = offset == largest_offset or offset == -(phase.overdue_every_days or 0)
        if announce:
            departments = {
                a.employee.current_version.department
                for a in agreements
                if a.employee.current_version and a.employee.current_version.department_id
            }
            for department in departments:
                collab_department = getattr(department, "collab_department_id", "") or ""
                if not collab_department:
                    continue
                key = f"{period.name}:{phase.stage}:announcement:{department.code}:{label}"
                if _already_sent(key):
                    continue
                if client is None:
                    if dry_run:
                        run.announcements_sent += 1
                    continue
                overdue = offset < 0
                client.publish_announcement(
                    title=(
                        f"{'OVERDUE: ' if overdue else ''}{period.name} "
                        f"{phase.get_stage_display().lower()} closes {phase.due_on:%d %b %Y}"
                    ),
                    body=(
                        f"Your {period.name} performance step is {'overdue' if overdue else 'open'}. "
                        f"Complete and sign it with your Head by {phase.due_on:%d %b %Y}. "
                        f"Open the HCM: {getattr(settings, 'HCM_PUBLIC_URL', '')}/my-performance"
                    ),
                    audience_type="department",
                    audience_ref=collab_department,
                    priority="critical",
                    requires_ack=True,
                    dedupe_key=f"hcm-{period.name.replace('/', '-')}-{phase.stage}-{label}-{department.code}",
                )
                run.announcements_sent += 1
                _record(period, phase.stage, ReminderLog.Kind.ANNOUNCEMENT, key, offset_days=offset,
                        detail=f"department {department.code}")
    except CollabError as exc:
        logger.warning("performance reminders: collab push failed: %s", exc)
        run.errors.append(str(exc))
    finally:
        if client is not None:
            client.close()

    return run
