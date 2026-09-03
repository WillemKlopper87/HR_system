from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from . import retention
from .models import AuditLogEntry, RetentionRule, RetentionRuleRun, RetentionRun, StepUpGrant
from .tiers import FieldTier


def _rule(entity_type, **fields):
    """Defaults for these entity types are seeded by migration 0007 — override, don't collide."""
    rule, _ = RetentionRule.objects.update_or_create(entity_type=entity_type, defaults=fields)
    return rule


def _old(dt, months):
    return dt - timedelta(days=31 * months)


class RetentionRegistryTests(TestCase):
    def test_register_and_lookup(self):
        calls = []

        def handler(*, cutoff, action, dry_run):
            calls.append((cutoff, action, dry_run))
            return 3

        with retention.temporary_handler("demo.Thing", handler):
            self.assertIs(retention.get_handler("demo.Thing"), handler)
        self.assertIsNone(retention.get_handler("demo.Thing"))

    def test_cutoff_subtracts_calendar_months(self):
        now = timezone.datetime(2026, 3, 31, 12, 0, tzinfo=timezone.timezone.utc)
        self.assertEqual(retention.cutoff_for(now, 1).date().isoformat(), "2026-02-28")
        self.assertEqual(retention.cutoff_for(now, 12).date().isoformat(), "2025-03-31")
        self.assertEqual(retention.cutoff_for(now, 13).date().isoformat(), "2025-02-28")


class RetentionRunTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        RetentionRule.objects.all().delete()  # start from no rules; migration 0007 seeds defaults

    def _audit(self, age_months):
        e = AuditLogEntry.objects.create(
            action=AuditLogEntry.Action.LOGIN, entity_type="auth.User", entity_id="1", field_tier=FieldTier.PUBLIC
        )
        # auto_now_add can't be overridden on create; push it back explicitly
        AuditLogEntry.objects.filter(pk=e.pk).update(timestamp=_old(self.now, age_months))
        return e

    def test_deletes_audit_entries_older_than_rule_period_only(self):
        old = self._audit(70)
        recent = self._audit(1)
        _rule("rbac_audit.AuditLogEntry", period_months=60, action=RetentionRule.Action.DELETE
        )
        results = retention.run_retention(now=self.now)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].entity_type, "rbac_audit.AuditLogEntry")
        self.assertEqual(results[0].affected, 1)
        self.assertFalse(AuditLogEntry.objects.filter(pk=old.pk).exists())
        self.assertTrue(AuditLogEntry.objects.filter(pk=recent.pk).exists())
        # the run itself is audit-logged (a fresh entry, not one of the two above)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                action=AuditLogEntry.Action.DELETE, entity_type="rbac_audit.AuditLogEntry", fields_touched__contains="retention"
            ).exists()
        )

    def test_dry_run_touches_nothing_and_logs_nothing(self):
        self._audit(70)
        _rule("rbac_audit.AuditLogEntry", period_months=60, action=RetentionRule.Action.DELETE
        )
        before = AuditLogEntry.objects.count()
        results = retention.run_retention(now=self.now, dry_run=True)
        self.assertEqual(results[0].affected, 1)
        self.assertTrue(results[0].dry_run)
        self.assertEqual(AuditLogEntry.objects.count(), before)

    def test_inactive_and_retain_rules_are_skipped(self):
        self._audit(70)
        _rule("rbac_audit.AuditLogEntry", period_months=60, action=RetentionRule.Action.DELETE, active=False
        )
        _rule("rbac_audit.StepUpGrant", period_months=1, action=RetentionRule.Action.RETAIN
        )
        results = retention.run_retention(now=self.now)
        self.assertEqual([r.status for r in results], ["skipped", "skipped"])
        self.assertEqual(AuditLogEntry.objects.count(), 1)

    def test_unknown_entity_type_is_reported_not_raised(self):
        _rule("nope.Nothing", period_months=1, action=RetentionRule.Action.DELETE)
        results = retention.run_retention(now=self.now)
        self.assertEqual(results[0].status, "no_handler")
        self.assertEqual(results[0].affected, 0)

    def test_handler_exception_is_isolated_per_rule(self):
        def boom(*, cutoff, action, dry_run):
            raise RuntimeError("bad handler")

        _rule("demo.Boom", period_months=1, action=RetentionRule.Action.DELETE)
        self._audit(70)
        _rule("rbac_audit.AuditLogEntry", period_months=60, action=RetentionRule.Action.DELETE
        )
        with retention.temporary_handler("demo.Boom", boom):
            results = {r.entity_type: r for r in retention.run_retention(now=self.now)}
        self.assertEqual(results["demo.Boom"].status, "error")
        self.assertIn("bad handler", results["demo.Boom"].detail)
        self.assertEqual(results["rbac_audit.AuditLogEntry"].affected, 1)

    def test_run_creates_a_durable_record_with_completed_at(self):
        _rule("rbac_audit.AuditLogEntry", period_months=60, action=RetentionRule.Action.DELETE)
        retention.run_retention(now=self.now)
        run = RetentionRun.objects.get()
        self.assertEqual(run.dry_run, False)
        self.assertIsNotNone(run.completed_at)
        self.assertGreaterEqual(run.completed_at, run.started_at)

    def test_no_handler_rule_is_durably_recorded_not_just_logged(self):
        _rule("nope.Nothing", period_months=1, action=RetentionRule.Action.DELETE)
        retention.run_retention(now=self.now)
        rule_run = RetentionRuleRun.objects.get(entity_type="nope.Nothing")
        self.assertEqual(rule_run.status, RetentionRuleRun.RunStatus.NO_HANDLER)

    def test_failed_rule_is_durably_recorded_not_just_logged(self):
        def boom(*, cutoff, action, dry_run):
            raise RuntimeError("bad handler")

        _rule("demo.Boom", period_months=1, action=RetentionRule.Action.DELETE)
        with retention.temporary_handler("demo.Boom", boom):
            retention.run_retention(now=self.now)

        rule_run = RetentionRuleRun.objects.get(entity_type="demo.Boom")
        self.assertEqual(rule_run.status, RetentionRuleRun.RunStatus.ERROR)
        self.assertIn("bad handler", rule_run.detail)

    def test_one_rule_failure_does_not_hide_other_results_in_the_durable_record(self):
        def boom(*, cutoff, action, dry_run):
            raise RuntimeError("bad handler")

        self._audit(70)
        _rule("demo.Boom", period_months=1, action=RetentionRule.Action.DELETE)
        _rule("rbac_audit.AuditLogEntry", period_months=60, action=RetentionRule.Action.DELETE)
        with retention.temporary_handler("demo.Boom", boom):
            retention.run_retention(now=self.now)

        run = RetentionRun.objects.get()
        statuses = {r.entity_type: r.status for r in run.rule_runs.all()}
        self.assertEqual(statuses["demo.Boom"], RetentionRuleRun.RunStatus.ERROR)
        self.assertEqual(statuses["rbac_audit.AuditLogEntry"], RetentionRuleRun.RunStatus.OK)

    def test_successive_runs_each_get_their_own_durable_record(self):
        _rule("rbac_audit.AuditLogEntry", period_months=60, action=RetentionRule.Action.DELETE)
        retention.run_retention(now=self.now)
        retention.run_retention(now=self.now)
        self.assertEqual(RetentionRun.objects.count(), 2)

    def test_expired_step_up_grants_are_purged(self):
        from datetime import date

        from core_hr.models import Employee

        emp = Employee.objects.create(
            employee_number="E9001", first_name="Ret", last_name="Ention", date_of_birth=date(1990, 1, 1),
            work_email="ret.ention@example.com", hire_date=date(2020, 1, 1),
        )
        old = StepUpGrant.objects.create(
            employee=emp, scope=StepUpGrant.Scope.PAYROLL_DATA, reason=StepUpGrant.Reason.PAYROLL_PROCESSING, expires_at=_old(self.now, 3)
        )
        live = StepUpGrant.objects.create(
            employee=emp, scope=StepUpGrant.Scope.PAYROLL_DATA, reason=StepUpGrant.Reason.PAYROLL_PROCESSING, expires_at=self.now + timedelta(minutes=10)
        )
        _rule("rbac_audit.StepUpGrant", period_months=1, action=RetentionRule.Action.DELETE
        )
        retention.run_retention(now=self.now)
        self.assertFalse(StepUpGrant.objects.filter(pk=old.pk).exists())
        self.assertTrue(StepUpGrant.objects.filter(pk=live.pk).exists())


class RetentionEntryPointsTests(TestCase):
    def test_management_command_dry_run_prints_summary(self):
        _rule("rbac_audit.AuditLogEntry", period_months=60, action=RetentionRule.Action.DELETE
        )
        from io import StringIO

        out = StringIO()
        call_command("run_retention", "--dry-run", stdout=out)
        self.assertIn("rbac_audit.AuditLogEntry", out.getvalue())
        self.assertIn("dry-run", out.getvalue())

    def test_celery_task_is_registered_and_runs_inline(self):
        from config.celery import app
        from .tasks import run_retention_task

        self.assertIn("rbac_audit.tasks.run_retention_task", app.tasks)
        with mock.patch.object(retention, "run_retention", return_value=[]) as run:
            self.assertEqual(
                run_retention_task.apply().get(),
                {"rules": 0, "affected": 0, "errors": [], "no_handler": []},
            )
            run.assert_called_once()

    def test_beat_schedule_includes_retention(self):
        from django.conf import settings

        self.assertIn("run-retention-daily", settings.CELERY_BEAT_SCHEDULE)
