"""PC-1 reminder engine (ADR-011): who gets nudged, when, exactly once.

The point of this feature, in the user's words, is that KPIs get forgotten
until it's a last-minute rush — so these tests pin the *schedule* behaviour
(which offset fires on which day, priority rising toward the deadline, overdue
repeats) and the *safety* behaviour (idempotent, never blocks when collab is
off or unreachable) rather than the wording of the messages.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import httpx
from django.test import TestCase, override_settings

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from integrations.collab import CollabClient, CollabConfig

from .models import (
    AgreementTemplate,
    PerformanceAgreement,
    PerformancePeriod,
    PeriodPhase,
    ReminderLog,
    TemplateElement,
    TemplateSection,
)
from .reminders import due_offset, priority_for, run_reminders
from .services import create_agreement, publish_template

LEVELS = {str(i): f"level {i}" for i in range(1, 6)}
CFG = CollabConfig(base_url="http://collab.test", api_key="k", max_attempts=2, backoff_seconds=0)


class FakeCollab:
    """Records what the reminder run pushed, so the tests can assert on the
    calls rather than on log lines."""

    def __init__(self, fail=False):
        self.items: dict[str, dict] = {}
        self.announcements: list[dict] = []
        self.projects: dict[str, str] = {}
        self.fail = fail

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            return httpx.Response(503, text="collab down")
        path = request.url.path
        if path == "/integrations/projects/ensure":
            body = json.loads(request.content)
            pid = f"p-{body['owning_department_id']}"
            self.projects[pid] = body["name"]
            return httpx.Response(200, json={"id": pid, "name": body["name"]})
        if path.startswith("/integrations/work-items/hcm/"):
            ref = path[len("/integrations/work-items/hcm/"):]
            body = json.loads(request.content)
            item = self.items.get(ref, {"id": f"wi-{len(self.items) + 1}", "external_ref": ref})
            item.update(body)
            self.items[ref] = item
            return httpx.Response(200, json=item)
        if path == "/integrations/announcements":
            body = json.loads(request.content)
            self.announcements.append(body)
            return httpx.Response(201, json={"id": f"a-{len(self.announcements)}", "created": True, **body})
        return httpx.Response(404, json={})


class ReminderScheduleTests(TestCase):
    def _phase(self, due_on, offsets=(28, 14, 7, 1), overdue_every=7):
        period = PerformancePeriod.objects.create(
            name="2026/27", start_date=date(2026, 4, 1), end_date=date(2027, 3, 31)
        )
        return PeriodPhase.objects.create(
            period=period, stage=PeriodPhase.Stage.CONTRACTING, opens_on=date(2026, 4, 1),
            due_on=due_on, reminder_offsets_days=list(offsets), overdue_every_days=overdue_every,
        )

    def test_offsets_fire_only_on_their_configured_days(self):
        phase = self._phase(date(2026, 4, 30))
        self.assertEqual(due_offset(phase, date(2026, 4, 2)), 28)
        self.assertEqual(due_offset(phase, date(2026, 4, 16)), 14)
        self.assertEqual(due_offset(phase, date(2026, 4, 29)), 1)
        self.assertIsNone(due_offset(phase, date(2026, 4, 3)))
        self.assertIsNone(due_offset(phase, date(2026, 4, 30)))  # 0 isn't in the ladder

    def test_overdue_repeats_on_the_configured_cadence(self):
        phase = self._phase(date(2026, 4, 30))
        self.assertEqual(due_offset(phase, date(2026, 5, 7)), -7)
        self.assertEqual(due_offset(phase, date(2026, 5, 14)), -14)
        self.assertIsNone(due_offset(phase, date(2026, 5, 8)))

    def test_priority_rises_toward_the_deadline(self):
        self.assertEqual(priority_for(28), "low")
        self.assertEqual(priority_for(14), "normal")
        self.assertEqual(priority_for(7), "high")
        self.assertEqual(priority_for(1), "urgent")
        self.assertEqual(priority_for(None), "urgent")  # overdue


@override_settings(COLLAB_ENABLED=True, COLLAB_BASE_URL="http://collab.test", COLLAB_API_KEY="k",
                   HCM_PUBLIC_URL="https://hcm.sentech.example.com")
class ReminderRunTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Operations", code="OPS", collab_department_id="d-ops")
        self.level = OccupationalLevel.objects.get(code="TOP")
        self.grade = JobGrade.objects.create(name="G1", code="G1", occupational_level=self.level)
        self.location = Location.objects.create(name="HO", code="HO", province=Location.Province.GAUTENG)
        self.head = self._hire("H1", "Head", collab_user_id="u-head")
        self.a = self._hire("E1", "Ann", manager=self.head, collab_user_id="u-1")
        self.b = self._hire("E2", "Ben", manager=self.head, collab_user_id="u-2")
        self.no_account = self._hire("E3", "Cara", manager=self.head, collab_user_id="")

        self.period = PerformancePeriod.objects.create(
            name="2026/27", start_date=date(2026, 4, 1), end_date=date(2027, 3, 31),
            status=PerformancePeriod.Status.CONTRACTING,
        )
        self.phase = PeriodPhase.objects.create(
            period=self.period, stage=PeriodPhase.Stage.CONTRACTING, opens_on=date(2026, 4, 1),
            due_on=date(2026, 4, 30), reminder_offsets_days=[28, 14, 7, 1], overdue_every_days=7,
        )
        self.template = self._template()
        for employee in (self.a, self.b, self.no_account):
            create_agreement(period=self.period, employee=employee, template=self.template)

    def _hire(self, number, first, manager=None, collab_user_id=""):
        employee = Employee.objects.hire(
            employee_number=number, first_name=first, last_name="Test", date_of_birth=date(1990, 1, 1),
            work_email=f"{first.lower()}@sentech.example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, manager=manager,
        )
        if collab_user_id:
            Employee.objects.filter(pk=employee.pk).update(collab_user_id=collab_user_id)
            employee.refresh_from_db()
        return employee

    def _template(self):
        template = AgreementTemplate.objects.create(name="Scorecard", version=1)
        section = TemplateSection.objects.create(template=template, title="Objective", order=0)
        TemplateElement.objects.create(
            template=template, section=section, kpi_title="KPI 1", default_weight=Decimal("1.0"),
            level_descriptors=dict(LEVELS),
        )
        return publish_template(template)

    def _run(self, fake, *, today=date(2026, 4, 16), **kw):
        client = CollabClient(CFG, transport=httpx.MockTransport(fake.handler), sleep=lambda s: None)
        from unittest.mock import patch

        with patch("performance.reminders.collab.get_client", return_value=client):
            return run_reminders(today=today, **kw)

    def test_one_work_item_per_outstanding_employee_plus_a_head_digest(self):
        fake = FakeCollab()
        run = self._run(fake)
        self.assertEqual(run.stage, "contracting")
        self.assertEqual(run.offset, 14)
        self.assertEqual(run.outstanding, 3)
        self.assertEqual(run.items_sent, 2)  # Cara has no collab account
        self.assertEqual(run.skipped_no_collab_account, ["E3"])
        self.assertEqual(run.digests_sent, 1)
        refs = sorted(self.items_refs(fake))
        self.assertEqual(len(refs), 3)  # 2 employee items + 1 head digest
        item = fake.items[[r for r in refs if r.startswith("hcm:agreement")][0]]
        self.assertEqual(item["priority"], "normal")  # T-14
        self.assertEqual(item["due_on"], "2026-04-30")
        self.assertIn("https://hcm.sentech.example.com/my-performance/agreements/", item["description"])
        digest = fake.items[[r for r in refs if r.startswith("hcm:head-digest")][0]]
        self.assertIn("3 of your team", digest["title"])
        self.assertEqual(digest["assignee_user_id"], "u-head")

    def test_running_twice_on_the_same_day_sends_nothing_new(self):
        fake = FakeCollab()
        first = self._run(fake)
        calls_after_first = len(fake.items)
        second = self._run(fake)
        self.assertEqual(second.items_sent, 0)
        self.assertEqual(second.digests_sent, 0)
        self.assertEqual(len(fake.items), calls_after_first)
        self.assertEqual(ReminderLog.objects.filter(kind="employee_item").count(), 3)  # incl. the "no account" note
        self.assertGreater(first.items_sent, 0)

    def test_a_signed_agreement_drops_out_of_the_next_batch(self):
        fake = FakeCollab()
        self._run(fake, today=date(2026, 4, 16))
        PerformanceAgreement.objects.filter(employee=self.a).update(status=PerformanceAgreement.Status.AGREED)
        run = self._run(fake, today=date(2026, 4, 23))  # T-7
        self.assertEqual(run.outstanding, 2)
        self.assertEqual(run.offset, 7)
        self.assertEqual(run.items_sent, 1)  # Ben only; Cara still unmapped

    def test_overdue_batch_is_urgent_and_announces_once(self):
        fake = FakeCollab()
        run = self._run(fake, today=date(2026, 5, 7))  # 7 days overdue
        self.assertEqual(run.offset, -7)
        item = fake.items[[r for r in fake.items if r.startswith("hcm:agreement")][0]]
        self.assertEqual(item["priority"], "urgent")
        self.assertEqual(len(fake.announcements), 1)
        self.assertEqual(fake.announcements[0]["priority"], "critical")
        self.assertTrue(fake.announcements[0]["title"].startswith("OVERDUE:"))
        self.assertEqual(fake.announcements[0]["audience_ref"], "d-ops")
        # a second run the same day announces nothing further
        self._run(fake, today=date(2026, 5, 7))
        self.assertEqual(len(fake.announcements), 1)

    def test_phase_open_batch_publishes_the_critical_announcement(self):
        fake = FakeCollab()
        run = self._run(fake, today=date(2026, 4, 2))  # T-28, the first offset
        self.assertEqual(run.offset, 28)
        self.assertEqual(run.announcements_sent, 1)
        self.assertEqual(fake.announcements[0]["audience_type"], "department")
        self.assertIn("2026/27", fake.announcements[0]["title"])

    def test_nothing_is_sent_when_no_offset_falls_today(self):
        fake = FakeCollab()
        run = self._run(fake, today=date(2026, 4, 3))
        self.assertIsNone(run.offset)
        self.assertEqual(run.items_sent, 0)
        self.assertEqual(fake.items, {})
        self.assertIn("No reminder offset", run.note)

    def test_collab_failure_is_reported_not_raised_and_can_be_retried(self):
        fake = FakeCollab(fail=True)
        run = self._run(fake)
        self.assertTrue(run.errors)
        self.assertEqual(run.items_sent, 0)
        # nothing was logged as sent, so the next run tries again
        self.assertEqual(ReminderLog.objects.filter(channel="collab").count(), 0)
        good = FakeCollab()
        retry = self._run(good)
        self.assertEqual(retry.items_sent, 2)

    @override_settings(COLLAB_ENABLED=False)
    def test_with_collab_off_the_run_still_reports_who_is_outstanding(self):
        run = run_reminders(today=date(2026, 4, 16))
        self.assertEqual(run.outstanding, 3)
        self.assertEqual(run.items_sent, 0)
        self.assertIn("Collab integration is off", run.note)

    def test_dry_run_touches_nothing(self):
        run = run_reminders(today=date(2026, 4, 16), dry_run=True)
        self.assertEqual(run.outstanding, 3)
        self.assertEqual(run.items_sent, 2)
        self.assertEqual(ReminderLog.objects.count(), 0)

    def test_celery_task_and_beat_entry_exist(self):
        from django.conf import settings

        from config.celery import app

        from .tasks import run_performance_reminders_task

        self.assertIn("performance.tasks.run_performance_reminders_task", app.tasks)
        self.assertIn("run-performance-reminders-daily", settings.CELERY_BEAT_SCHEDULE)
        result = run_performance_reminders_task.apply(kwargs={"dry_run": True}).get()
        self.assertIn("outstanding", result)

    @staticmethod
    def items_refs(fake) -> list[str]:
        return list(fake.items)
