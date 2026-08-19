"""H3 ops/observability: /healthz stays process-up-only; /readyz actually
checks DB + cache connectivity."""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase


class HealthzTests(TestCase):
    def test_healthz_reports_ok_without_checking_anything(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class ReadyzTests(TestCase):
    def test_readyz_reports_ready_when_db_and_cache_are_reachable(self):
        response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["checks"], {"database": "ok", "cache": "ok"})

    def test_readyz_reports_503_when_the_database_is_unreachable(self):
        with patch("config.urls.connections") as mock_connections:
            mock_connections.__getitem__.side_effect = Exception("connection refused")
            response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "not_ready")
        self.assertEqual(body["checks"]["database"], "unreachable")

    def test_readyz_reports_503_when_the_cache_is_unreachable(self):
        with patch("config.urls.cache") as mock_cache:
            mock_cache.set.side_effect = Exception("cache down")
            response = self.client.get("/readyz")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "not_ready")
        self.assertEqual(body["checks"]["cache"], "unreachable")
        self.assertEqual(body["checks"]["database"], "ok")
