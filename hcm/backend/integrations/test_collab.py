"""Contract tests for integrations/collab.py against a recorded shape of the
collab platform's /integrations surface (X0 in that repo, its
app/tests/test_integrations.py is the other half of this contract).
No network: httpx.MockTransport plays the collab side."""
from __future__ import annotations

import json
from datetime import date

import httpx
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from core_hr.models import Department, Employee

from . import collab
from .collab import CollabClient, CollabConfig, CollabError
from .sync import sync_collab_ids

CFG = CollabConfig(base_url="http://collab.test", api_key="k", timeout=1, max_attempts=3, backoff_seconds=0.01)


class FakeCollab:
    """Just enough of the collab platform to exercise the client: keyed
    upserts, dedupe'd announcements, users by email, a department list."""

    def __init__(self):
        self.users = {"thandi@sentech.example.com": "u-1", "sipho@sentech.example.com": "u-2"}
        self.departments = [{"id": "d-ops", "name": "Operations"}, {"id": "d-fin", "name": "Finance"}]
        self.items: dict[str, dict] = {}
        self.announcements: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail_next: list[int] = []  # status codes to return before succeeding

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, request.url.path))
        if request.headers.get("X-Api-Key") != "k":
            return httpx.Response(401, json={"detail": "Invalid API key"})
        if self.fail_next:
            return httpx.Response(self.fail_next.pop(0), text="upstream hiccup")
        path = request.url.path
        if path.startswith("/users/by-email/"):
            email = path.rsplit("/", 1)[1]
            uid = self.users.get(email)
            return httpx.Response(200, json={"id": uid, "email": email}) if uid else httpx.Response(404, json={})
        if path == "/departments":
            return httpx.Response(200, json=self.departments)
        if path == "/integrations/projects/ensure":
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": f"p-{body['owning_department_id']}", "name": body["name"]})
        if path.startswith("/integrations/work-items/hcm/"):
            ref = path[len("/integrations/work-items/hcm/"):]
            if request.method == "GET":
                item = self.items.get(ref)
                return httpx.Response(200, json=item) if item else httpx.Response(404, json={})
            body = json.loads(request.content)
            item = self.items.get(ref) or {"id": f"wi-{len(self.items) + 1}", "external_ref": ref}
            item.update({k: v for k, v in body.items() if v is not None})
            self.items[ref] = item
            return httpx.Response(200, json=item)
        if path == "/integrations/announcements":
            body = json.loads(request.content)
            key = body.get("dedupe_key") or f"nokey-{len(self.announcements)}"
            if key in self.announcements:
                return httpx.Response(201, json={**self.announcements[key], "created": False})
            ann = {"id": f"a-{len(self.announcements) + 1}", "title": body["title"], "created": True}
            self.announcements[key] = ann
            return httpx.Response(201, json=ann)
        return httpx.Response(404, json={"detail": "nope"})


def _client(fake: FakeCollab, cfg: CollabConfig = CFG) -> CollabClient:
    return CollabClient(cfg, transport=httpx.MockTransport(fake.handler), sleep=lambda s: None)


class CollabClientContractTests(SimpleTestCase):
    def test_upsert_is_keyed_and_repeatable(self):
        fake = FakeCollab()
        c = _client(fake)
        first = c.upsert_work_item(
            "hcm:agreement:1:contracting", project_id="p-d-ops", title="Sign your agreement",
            assignee_email="thandi@sentech.example.com", due_on=date(2026, 4, 30),
        )
        second = c.upsert_work_item(
            "hcm:agreement:1:contracting", project_id="p-d-ops", title="Sign your agreement",
            assignee_email="thandi@sentech.example.com", due_on=date(2026, 4, 30), priority="urgent",
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["priority"], "urgent")
        self.assertEqual(len(fake.items), 1)
        closed = c.close_work_item("hcm:agreement:1:contracting", project_id="p-d-ops", title="Sign your agreement")
        self.assertEqual(closed["status"], "done")
        self.assertEqual(c.get_work_item("hcm:agreement:1:contracting")["id"], first["id"])
        self.assertIsNone(c.get_work_item("hcm:agreement:404:contracting"))

    def test_announcement_dedupe_round_trip(self):
        fake = FakeCollab()
        c = _client(fake)
        a1 = c.publish_announcement(title="Contracting open", body="Sign by 30 April", audience_type="department",
                                    audience_ref="d-ops", priority="critical", dedupe_key="hcm-2026-27-open")
        a2 = c.publish_announcement(title="Contracting open", body="Sign by 30 April", audience_type="department",
                                    audience_ref="d-ops", priority="critical", dedupe_key="hcm-2026-27-open")
        self.assertTrue(a1["created"])
        self.assertFalse(a2["created"])
        self.assertEqual(a1["id"], a2["id"])

    def test_transient_failures_are_retried_with_backoff_then_succeed(self):
        fake = FakeCollab()
        fake.fail_next = [503, 502]
        sleeps: list[float] = []
        c = CollabClient(CFG, transport=httpx.MockTransport(fake.handler), sleep=sleeps.append)
        self.assertEqual(c.lookup_user_id("thandi@sentech.example.com"), "u-1")
        self.assertEqual(sleeps, [0.01, 0.02])  # exponential backoff between the 3 attempts

    def test_exhausted_retries_raise_collab_error_with_status(self):
        fake = FakeCollab()
        fake.fail_next = [500, 500, 500]
        c = _client(fake)
        with self.assertRaises(CollabError) as ctx:
            c.list_departments()
        self.assertEqual(ctx.exception.status, 500)
        self.assertEqual(len(fake.calls), 3)

    def test_non_retryable_errors_fail_fast(self):
        fake = FakeCollab()
        c = CollabClient(CollabConfig(base_url="http://collab.test", api_key="wrong", backoff_seconds=0),
                         transport=httpx.MockTransport(fake.handler), sleep=lambda s: None)
        with self.assertRaises(CollabError) as ctx:
            c.list_departments()
        self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(len(fake.calls), 1)  # no retry on 401

    def test_connection_errors_are_retried_then_raised(self):
        def boom(request):
            raise httpx.ConnectError("refused")

        c = CollabClient(CFG, transport=httpx.MockTransport(boom), sleep=lambda s: None)
        with self.assertRaises(CollabError):
            c.lookup_user_id("x@y.z")

    @override_settings(COLLAB_ENABLED=False)
    def test_get_client_is_none_when_disabled(self):
        self.assertIsNone(collab.get_client())

    @override_settings(COLLAB_ENABLED=True, COLLAB_BASE_URL="", COLLAB_API_KEY="")
    def test_get_client_is_none_when_enabled_but_unconfigured(self):
        self.assertIsNone(collab.get_client())

    @override_settings(COLLAB_ENABLED=True, COLLAB_BASE_URL="http://collab.test/", COLLAB_API_KEY="k")
    def test_get_client_when_configured(self):
        c = collab.get_client()
        self.assertIsNotNone(c)
        self.assertEqual(c.config.base_url, "http://collab.test")
        c.close()


class SyncCollabIdsTests(TestCase):
    def setUp(self):
        self.ops = Department.objects.create(name="Operations", code="OPS")
        self.hr = Department.objects.create(name="Human Resources", code="HR")
        self.thandi = Employee.objects.create(
            employee_number="E1", first_name="Thandi", last_name="M", date_of_birth=date(1990, 1, 1),
            work_email="thandi@sentech.example.com", hire_date=date(2020, 1, 1),
        )
        self.nobody = Employee.objects.create(
            employee_number="E2", first_name="No", last_name="Account", date_of_birth=date(1990, 1, 1),
            work_email="nobody@sentech.example.com", hire_date=date(2020, 1, 1),
        )

    def test_sync_maps_by_email_and_name_and_reports_unmatched(self):
        fake = FakeCollab()
        result = sync_collab_ids(_client(fake))
        self.thandi.refresh_from_db()
        self.nobody.refresh_from_db()
        self.ops.refresh_from_db()
        self.hr.refresh_from_db()
        self.assertEqual(self.thandi.collab_user_id, "u-1")
        self.assertEqual(self.nobody.collab_user_id, "")
        self.assertEqual(self.ops.collab_department_id, "d-ops")
        self.assertEqual(self.hr.collab_department_id, "")
        self.assertEqual(result.employees_matched, 1)
        self.assertEqual(result.employees_unmatched, ["nobody@sentech.example.com"])
        self.assertEqual(result.departments_unmatched, ["Human Resources"])

    def test_dry_run_writes_nothing(self):
        result = sync_collab_ids(_client(FakeCollab()), dry_run=True)
        self.thandi.refresh_from_db()
        self.assertEqual(self.thandi.collab_user_id, "")
        self.assertEqual(result.employees_matched, 1)

    def test_only_missing_skips_already_mapped_rows(self):
        Employee.objects.filter(pk=self.thandi.pk).update(collab_user_id="already")
        fake = FakeCollab()
        sync_collab_ids(_client(fake))
        self.thandi.refresh_from_db()
        self.assertEqual(self.thandi.collab_user_id, "already")
        self.assertNotIn(("GET", "/users/by-email/thandi@sentech.example.com"), fake.calls)

    @override_settings(COLLAB_ENABLED=False)
    def test_command_refuses_when_disabled(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("sync_collab_ids", "--dry-run")
