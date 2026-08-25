"""C1 part 3 slice 3: the hire/exit-completion registry that lets
onboarding (a domain app) hang a checklist off hire() and exit execution
without core_hr ever importing it. Same shape and same test style as
core_hr/test_access_cascade_registry.py -- these cover the registry
mechanics and failure isolation directly; end-to-end behaviour (the
handlers actually running as part of a real hire/exit) lives in
onboarding/test_checklists.py.
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase

from . import lifecycle_hooks
from .models import Employee
from .tests import _seed_reference_data


class HireHandlerRegistryTests(TestCase):
    def test_register_and_lookup(self):
        def handler(employee):
            return 0

        with lifecycle_hooks.temporary_hire_handler("demo.thing", handler):
            self.assertIn("demo.thing", lifecycle_hooks.registered_hire_handlers())
        self.assertNotIn("demo.thing", lifecycle_hooks.registered_hire_handlers())

    def test_temporary_hire_handler_restores_previous_on_exit(self):
        def original(employee):
            return 1

        def replacement(employee):
            return 2

        lifecycle_hooks.register_hire_handler("demo.thing", original)
        try:
            with lifecycle_hooks.temporary_hire_handler("demo.thing", replacement):
                self.assertIn("demo.thing", lifecycle_hooks.registered_hire_handlers())
            self.assertIn("demo.thing", lifecycle_hooks.registered_hire_handlers())
        finally:
            lifecycle_hooks.unregister_hire_handler("demo.thing")
        self.assertNotIn("demo.thing", lifecycle_hooks.registered_hire_handlers())


class ExitCompletionHandlerRegistryTests(TestCase):
    def test_register_and_lookup(self):
        def handler(employee, change):
            return 0

        with lifecycle_hooks.temporary_exit_completion_handler("demo.thing", handler):
            self.assertIn("demo.thing", lifecycle_hooks.registered_exit_completion_handlers())
        self.assertNotIn("demo.thing", lifecycle_hooks.registered_exit_completion_handlers())


class RunHandlersTests(TestCase):
    def setUp(self):
        self.dept, _, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E0091", first_name="Life", last_name="Cycle", date_of_birth=date(1990, 1, 1),
            work_email="life.cycle@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_run_hire_handlers_reports_the_affected_count_per_handler(self):
        def handler(employee):
            return 3

        with lifecycle_hooks.temporary_hire_handler("demo.counted", handler):
            result = lifecycle_hooks.run_hire_handlers(self.employee)
        self.assertEqual(result["demo.counted"], 3)

    def test_a_failing_hire_handler_is_isolated_and_absent_from_the_result(self):
        def boom(employee):
            raise RuntimeError("bad handler")

        def fine(employee):
            return 1

        with (
            lifecycle_hooks.temporary_hire_handler("demo.boom", boom),
            lifecycle_hooks.temporary_hire_handler("demo.fine", fine),
        ):
            result = lifecycle_hooks.run_hire_handlers(self.employee)

        self.assertNotIn("demo.boom", result)
        self.assertEqual(result["demo.fine"], 1)

    def test_a_failing_exit_completion_handler_is_isolated_from_siblings(self):
        class _FakeChange:
            pk = "fake"

        def boom(employee, change):
            raise RuntimeError("bad handler")

        def fine(employee, change):
            return 2

        with (
            lifecycle_hooks.temporary_exit_completion_handler("demo.boom", boom),
            lifecycle_hooks.temporary_exit_completion_handler("demo.fine", fine),
        ):
            result = lifecycle_hooks.run_exit_completion_handlers(self.employee, _FakeChange())

        self.assertNotIn("demo.boom", result)
        self.assertEqual(result["demo.fine"], 2)


class HireActuallyRunsTheRegistryTests(TestCase):
    """Confirms EmployeeManager.hire() genuinely calls run_hire_handlers,
    not just that the registry mechanics work in isolation."""

    def test_hire_invokes_registered_handlers(self):
        dept, _, level, grade, location = _seed_reference_data()
        seen = []

        def handler(employee):
            seen.append(employee.employee_number)
            return 1

        with lifecycle_hooks.temporary_hire_handler("demo.probe", handler):
            Employee.objects.hire(
                employee_number="E0092", first_name="Hire", last_name="Probe", date_of_birth=date(1990, 1, 1),
                work_email="hire.probe@example.com", hire_date=date(2024, 1, 1), department=dept,
                occupational_level=level, job_grade=grade, location=location,
            )

        self.assertEqual(seen, ["E0092"])


class OnboardingHandlersAreWiredUpTests(TestCase):
    """Confirms OnboardingConfig.ready() actually registered its handlers
    under the name the registry dispatches by -- not just that the handler
    functions exist."""

    def test_onboarding_handlers_are_registered(self):
        self.assertIn("onboarding.ChecklistInstance", lifecycle_hooks.registered_hire_handlers())
        self.assertIn("onboarding.ChecklistInstance", lifecycle_hooks.registered_exit_completion_handlers())
