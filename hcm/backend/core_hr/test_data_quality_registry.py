"""H3: the data-quality sweep generalized from a single core_hr function into
a registry other apps plug into (rbac_audit.retention's shape, reused). These
tests cover the registry mechanics and isolation directly; `test_data_quality.py`-style
coverage of the *checks themselves* lives in each owning app.
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase

from . import data_quality
from .models import DataQualityException, Employee
from .tests import _seed_reference_data


class DataQualityRegistryTests(TestCase):
    def test_register_and_lookup(self):
        def handler():
            return []

        with data_quality.temporary_handler("demo.thing", handler):
            self.assertIs(data_quality.get_handler("demo.thing"), handler)
            self.assertIn("demo.thing", data_quality.registered_exception_types())
        self.assertIsNone(data_quality.get_handler("demo.thing"))
        self.assertNotIn("demo.thing", data_quality.registered_exception_types())

    def test_temporary_handler_restores_previous_on_exit(self):
        def original():
            return []

        def replacement():
            return []

        data_quality.register("demo.thing", original)
        try:
            with data_quality.temporary_handler("demo.thing", replacement):
                self.assertIs(data_quality.get_handler("demo.thing"), replacement)
            self.assertIs(data_quality.get_handler("demo.thing"), original)
        finally:
            data_quality.unregister("demo.thing")


class DataQualityRegisteredHandlerRunTests(TestCase):
    def setUp(self):
        self.dept, _, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E0040", first_name="Reg", last_name="Istered", date_of_birth=date(1990, 1, 1),
            work_email="reg.istered@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_registered_handler_opens_and_auto_resolves(self):
        flag = {"on": True}

        def handler():
            if flag["on"]:
                yield self.employee, "demo detail"

        with data_quality.temporary_handler("demo.thing", handler):
            data_quality.run_data_quality_checks()
            self.assertTrue(
                DataQualityException.objects.filter(
                    employee=self.employee, exception_type="demo.thing", resolved_at__isnull=True
                ).exists()
            )

            flag["on"] = False
            data_quality.run_data_quality_checks()
            self.assertFalse(
                DataQualityException.objects.filter(
                    employee=self.employee, exception_type="demo.thing", resolved_at__isnull=True
                ).exists()
            )
            self.assertTrue(
                DataQualityException.objects.filter(
                    employee=self.employee, exception_type="demo.thing", resolved_at__isnull=False
                ).exists()
            )

    def test_failing_handler_is_isolated_from_the_rest_of_the_sweep(self):
        def boom():
            raise RuntimeError("bad handler")
            yield  # pragma: no cover - makes this a generator function

        def fine():
            yield self.employee, "still works"

        with data_quality.temporary_handler("demo.boom", boom), data_quality.temporary_handler("demo.fine", fine):
            result = data_quality.run_data_quality_checks()

        self.assertTrue(
            DataQualityException.objects.filter(
                employee=self.employee, exception_type="demo.fine", resolved_at__isnull=True
            ).exists()
        )
        self.assertFalse(
            DataQualityException.objects.filter(exception_type="demo.boom").exists()
        )
        self.assertGreaterEqual(result["open_exceptions"], 1)


class RegisteredAppHandlersAreWiredUpTests(TestCase):
    """Confirms `AppConfig.ready()` in performance/compensation actually
    registered their handlers under the right ExceptionType -- not just that
    the handler functions exist."""

    def test_performance_and_compensation_handlers_are_registered(self):
        self.assertIsNotNone(
            data_quality.get_handler(DataQualityException.ExceptionType.PERFORMANCE_OVERDUE)
        )
        self.assertIsNotNone(
            data_quality.get_handler(DataQualityException.ExceptionType.COMP_PROPOSAL_STALE)
        )
