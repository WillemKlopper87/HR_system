from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.conf import settings
import yaml

from config.operational_metrics import (
    record_api_request,
    record_integration,
    record_notification_email,
    render_prometheus,
)
from config.task_metrics import record_task_failure, record_task_success
from integrations.tasks import sync_collab_ids_task

TOKEN = "metrics-test-token-that-is-at-least-32-characters"


@override_settings(METRICS_BEARER_TOKEN=TOKEN)
class MetricsEndpointTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_metrics_require_the_dedicated_bearer_token(self):
        self.assertEqual(self.client.get("/metrics").status_code, 404)
        self.assertEqual(self.client.get("/metrics", HTTP_AUTHORIZATION="Bearer wrong").status_code, 404)
        response = self.client.get("/metrics", HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertEqual(self.client.post("/metrics", HTTP_AUTHORIZATION=f"Bearer {TOKEN}").status_code, 405)

    @override_settings(METRICS_BEARER_TOKEN="too-short")
    def test_weak_metrics_token_keeps_endpoint_disabled(self):
        self.assertEqual(
            self.client.get("/metrics", HTTP_AUTHORIZATION="Bearer too-short").status_code,
            404,
        )

    def test_api_request_counters_and_latency_are_low_cardinality(self):
        record_api_request(method="GET", status_code=200, duration_seconds=0.125)
        record_api_request(method="TRACE", status_code=503, duration_seconds=0.25)
        body = render_prometheus()
        self.assertIn('hcm_api_requests_total{method="GET",status_class="2xx"} 1', body)
        self.assertIn('hcm_api_requests_total{method="OTHER",status_class="5xx"} 1', body)
        self.assertIn("hcm_api_request_duration_seconds_sum 0.375000", body)
        self.assertIn("hcm_api_request_duration_seconds_count 2", body)
        self.assertNotIn("path=", body)

    def test_api_middleware_records_real_api_response(self):
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 403)
        body = self.client.get("/metrics", HTTP_AUTHORIZATION=f"Bearer {TOKEN}").content.decode()
        self.assertIn('hcm_api_requests_total{method="GET",status_class="4xx"} 1', body)

    def test_tracked_task_signals_record_outcome_and_freshness(self):
        task = SimpleNamespace(name="rbac_audit.tasks.run_retention_task")
        record_task_success(sender=task)
        record_task_failure(sender=task)
        body = render_prometheus()
        self.assertIn(
            'hcm_background_task_runs_total{task="rbac_audit.tasks.run_retention_task",outcome="success"} 1',
            body,
        )
        self.assertIn(
            'hcm_background_task_runs_total{task="rbac_audit.tasks.run_retention_task",outcome="failure"} 1',
            body,
        )
        self.assertRegex(
            body,
            r'hcm_background_task_last_success_timestamp_seconds\{task="rbac_audit.tasks.run_retention_task"\} [1-9]\d*',
        )

    def test_notification_and_integration_metrics_have_no_payload_labels(self):
        record_notification_email("attempt")
        record_notification_email("failure")
        record_integration("collab", "attempt")
        record_integration("collab", "success")
        body = render_prometheus()
        self.assertIn('hcm_notification_email_total{outcome="failure"} 1', body)
        self.assertIn('hcm_integration_sync_total{integration="collab",outcome="success"} 1', body)
        self.assertNotIn("recipient", body)
        self.assertNotIn("employee", body)

    @patch("integrations.tasks.collab.get_client", return_value=None)
    def test_disabled_integration_records_attempt_and_skip(self, _get_client):
        self.assertEqual(sync_collab_ids_task.run(), {"skipped": "collab integration disabled"})
        body = render_prometheus()
        self.assertIn('hcm_integration_sync_total{integration="collab",outcome="attempt"} 1', body)
        self.assertIn('hcm_integration_sync_total{integration="collab",outcome="skipped"} 1', body)

    @patch("integrations.tasks.sync_collab_ids", side_effect=RuntimeError("provider unavailable"))
    @patch("integrations.tasks.collab.get_client")
    def test_integration_failure_records_failure_and_closes_client(self, get_client, _sync):
        client = Mock()
        get_client.return_value = client
        with self.assertRaises(RuntimeError):
            sync_collab_ids_task.run()
        client.close.assert_called_once_with()
        self.assertIn(
            'hcm_integration_sync_total{integration="collab",outcome="failure"} 1',
            render_prometheus(),
        )

    def test_dashboard_and_alert_rule_artifacts_are_parseable_and_complete(self):
        observability_dir = settings.BASE_DIR.parent / "ops" / "observability"
        dashboard = json.loads((observability_dir / "grafana-dashboard.json").read_text(encoding="utf-8"))
        rules = yaml.safe_load((observability_dir / "prometheus-rules.yml").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(dashboard["panels"]), 6)
        alert_names = {rule["alert"] for group in rules["groups"] for rule in group["rules"]}
        self.assertTrue({
            "HcmMetricsTargetDown", "HcmApiFiveXxRatioHigh", "HcmScheduledTaskStale",
            "HcmNotificationEmailFailures", "HcmCollabIntegrationStale",
        }.issubset(alert_names))
