"""C1 part 3: the access-cascade registry that lets identity_verification
(a domain app) plug into the employment-exit cascade without core_hr ever
importing it. Same shape and same test style as
core_hr/test_data_quality_registry.py -- these cover the registry
mechanics and failure isolation directly; end-to-end cascade behaviour
(the handlers actually running as part of a real exit) lives in
core_hr/test_exits.py.
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase

from . import access_cascade
from .models import Employee
from .tests import _seed_reference_data


class AccessCascadeExitRegistryTests(TestCase):
    def test_register_and_lookup(self):
        def handler(employee):
            return 0

        with access_cascade.temporary_exit_handler("demo.thing", handler):
            self.assertIn("demo.thing", access_cascade.registered_exit_handlers())
        self.assertNotIn("demo.thing", access_cascade.registered_exit_handlers())

    def test_temporary_exit_handler_restores_previous_on_exit(self):
        def original(employee):
            return 1

        def replacement(employee):
            return 2

        access_cascade.register_exit_handler("demo.thing", original)
        try:
            with access_cascade.temporary_exit_handler("demo.thing", replacement):
                self.assertIn("demo.thing", access_cascade.registered_exit_handlers())
            # Restored, not left unregistered.
            self.assertIn("demo.thing", access_cascade.registered_exit_handlers())
        finally:
            access_cascade.unregister_exit_handler("demo.thing")
        self.assertNotIn("demo.thing", access_cascade.registered_exit_handlers())


class AccessCascadeRestoreRegistryTests(TestCase):
    def test_register_and_lookup(self):
        def handler(employee):
            return 0

        with access_cascade.temporary_restore_handler("demo.thing", handler):
            self.assertIn("demo.thing", access_cascade.registered_restore_handlers())
        self.assertNotIn("demo.thing", access_cascade.registered_restore_handlers())


class AccessCascadeRunTests(TestCase):
    def setUp(self):
        self.dept, _, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E0041", first_name="Cas", last_name="Cade", date_of_birth=date(1990, 1, 1),
            work_email="cas.cade@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_run_exit_handlers_reports_the_affected_count_per_handler(self):
        def handler(employee):
            return 3

        with access_cascade.temporary_exit_handler("demo.counted", handler):
            result = access_cascade.run_exit_handlers(self.employee)
        self.assertEqual(result["demo.counted"], 3)

    def test_a_failing_exit_handler_is_isolated_and_absent_from_the_result(self):
        def boom(employee):
            raise RuntimeError("bad handler")

        def fine(employee):
            return 1

        with (
            access_cascade.temporary_exit_handler("demo.boom", boom),
            access_cascade.temporary_exit_handler("demo.fine", fine),
        ):
            result = access_cascade.run_exit_handlers(self.employee)

        self.assertNotIn("demo.boom", result)
        self.assertEqual(result["demo.fine"], 1)

    def test_a_failing_restore_handler_is_isolated_from_siblings(self):
        def boom(employee):
            raise RuntimeError("bad restore handler")

        def fine(employee):
            return 2

        with (
            access_cascade.temporary_restore_handler("demo.boom", boom),
            access_cascade.temporary_restore_handler("demo.fine", fine),
        ):
            result = access_cascade.run_restore_handlers(self.employee)

        self.assertNotIn("demo.boom", result)
        self.assertEqual(result["demo.fine"], 2)


class IdentityVerificationHandlersAreWiredUpTests(TestCase):
    """Confirms IdentityVerificationConfig.ready() actually registered its
    handlers under the name the cascade dispatches by -- not just that the
    handler functions exist."""

    def test_biometric_enrollment_handlers_are_registered(self):
        self.assertIn(
            "identity_verification.BiometricEnrollment", access_cascade.registered_exit_handlers()
        )
        self.assertIn(
            "identity_verification.BiometricEnrollment", access_cascade.registered_restore_handlers()
        )
