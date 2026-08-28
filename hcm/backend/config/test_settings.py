"""H2 (2026-08-28 fix): unit coverage for the pure fail-fast guard itself.
The guard runs at settings-module IMPORT time (inside `if not DEBUG:`),
which a normal Django TestCase can't re-trigger via override_settings --
that end-to-end behaviour (the actual process refusing to start) is
instead proven by a subprocess check in hcm-ci.yml's
backend-production-config job, not here."""
from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings import _require_production_secret


class RequireProductionSecretTests(SimpleTestCase):
    def test_rejects_the_known_development_default(self):
        with self.assertRaises(ImproperlyConfigured):
            _require_production_secret("X", "dev-default", "dev-default")

    def test_rejects_empty_value(self):
        with self.assertRaises(ImproperlyConfigured):
            _require_production_secret("X", "", "dev-default")

    def test_rejects_a_value_below_the_minimum_length(self):
        with self.assertRaises(ImproperlyConfigured):
            _require_production_secret("X", "short-but-not-the-dev-default", "dev-default", min_length=32)

    def test_accepts_a_long_unique_value(self):
        _require_production_secret("X", "a" * 40, "dev-default", min_length=32)
