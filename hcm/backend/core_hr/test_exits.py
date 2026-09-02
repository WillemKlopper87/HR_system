"""C1 part 3 -- employment exit state machine + access cascade
(docs/superpowers/specs/2026-08-20-employment-exit-states-design.md).
Spec §9 lists the required tests; this file treats that list as a floor,
not a ceiling."""
from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from identity_verification.models import BiometricEnrollment, LivenessCheck
from rbac_audit.models import AuditLogEntry, RetentionRule, Role, RoleAssignment
from rbac_audit.permissions import active_roles_for
from rest_framework.test import APIClient

from . import access_cascade
from .exits import (
    EmploymentChangeError,
    cancel_employment_change,
    confirm_employment_change,
    execute_due_employment_changes,
    execute_employment_change,
    propose_employment_change,
)
from .models import (
    ContractRenewalDecision,
    Department,
    Employee,
    EmployeeVersion,
    EmploymentChange,
    EmploymentEvent,
    JobGrade,
    Location,
    OccupationalLevel,
)

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG-X")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="GX1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HOX", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class ExitTestCase(TestCase):
    """Shared fixture: two hr_admins (so tiered confirmation has a
    genuinely different second person available) and one employee under
    test who holds a couple of roles and a Django login."""

    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.dept, self.level, self.grade, self.location = dept, level, grade, location

        self.hr_admin_1 = Employee.objects.hire(
            employee_number="HRA1", first_name="First", last_name="Admin", date_of_birth=date(1980, 1, 1),
            work_email="hra1@example.com", hire_date=date(2010, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hra1", password="x"),
        )
        self.hr_admin_2 = Employee.objects.hire(
            employee_number="HRA2", first_name="Second", last_name="Admin", date_of_birth=date(1981, 1, 1),
            work_email="hra2@example.com", hire_date=date(2011, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="hra2", password="x"),
        )
        for admin in (self.hr_admin_1, self.hr_admin_2):
            RoleAssignment.objects.create(employee=admin, role=Role.objects.get(name="hr_admin"))

        self.employee = Employee.objects.hire(
            employee_number="E700", first_name="Departing", last_name="Person", date_of_birth=date(1990, 5, 1),
            work_email="departing@example.com", hire_date=date(2020, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            user=User.objects.create_user(username="departing", password="x"),
        )
        self.role_manager = Role.objects.get(name="line_manager")
        self.role_employee = Role.objects.get(name="employee")
        RoleAssignment.objects.create(employee=self.employee, role=self.role_employee)
        RoleAssignment.objects.create(employee=self.employee, role=self.role_manager)

    def _propose(self, **kwargs):
        defaults = dict(
            employee=self.employee, actor=self.hr_admin_1,
            effective_date=timezone.localdate(), reason="Test reason.",
        )
        defaults.update(kwargs)
        return propose_employment_change(**defaults)


class ProposeConfirmCancelStateMachineTests(ExitTestCase):
    def test_propose_creates_a_proposed_change(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION)
        self.assertEqual(change.state, EmploymentChange.State.PROPOSED)
        self.assertEqual(change.proposed_by, self.hr_admin_1)
        self.assertIsNotNone(change.proposed_at)

    def test_reason_is_required(self):
        with self.assertRaises(EmploymentChangeError):
            self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION, reason="")
        with self.assertRaises(EmploymentChangeError):
            self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION, reason="   ")

    def test_invalid_change_type_rejected(self):
        with self.assertRaises(EmploymentChangeError):
            self._propose(change_type="not_a_real_type")

    def test_only_one_open_change_per_employee_at_a_time(self):
        self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION)
        with self.assertRaises(EmploymentChangeError):
            self._propose(change_type=EmploymentChange.ChangeType.RETIREMENT)

    def test_a_new_change_is_allowed_once_the_prior_one_is_terminal(self):
        first = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION)
        cancel_employment_change(first, actor=self.hr_admin_1)
        # Now that the only prior change is CANCELLED (terminal), a new one is fine.
        second = self._propose(change_type=EmploymentChange.ChangeType.RETIREMENT)
        self.assertEqual(second.state, EmploymentChange.State.PROPOSED)

    def test_routine_type_proposer_can_confirm_themselves(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION)
        confirm_employment_change(change, actor=self.hr_admin_1)
        change.refresh_from_db()
        self.assertEqual(change.confirmed_by, self.hr_admin_1)

    def test_tiered_type_same_person_confirm_is_rejected(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.DISMISSAL_MISCONDUCT)
        with self.assertRaises(EmploymentChangeError):
            confirm_employment_change(change, actor=self.hr_admin_1)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.PROPOSED)

    def test_tiered_type_different_person_confirm_is_accepted(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.DISMISSAL_MISCONDUCT)
        confirm_employment_change(change, actor=self.hr_admin_2)
        change.refresh_from_db()
        self.assertEqual(change.confirmed_by, self.hr_admin_2)

    def test_cannot_confirm_twice(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION)
        confirm_employment_change(change, actor=self.hr_admin_1)
        with self.assertRaises(EmploymentChangeError):
            confirm_employment_change(change, actor=self.hr_admin_1)

    def test_cancel_from_proposed_leaves_access_untouched(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION)
        cancel_employment_change(change, actor=self.hr_admin_1, reason="Mis-captured.")
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.CANCELLED)
        self.assertTrue(RoleAssignment.objects.filter(employee=self.employee, revoked_at__isnull=True).exists())
        self.employee.user.refresh_from_db()
        self.assertTrue(self.employee.user.is_active)

    def test_cancel_from_confirmed_future_dated_leaves_access_untouched(self):
        future = timezone.localdate() + timedelta(days=30)
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION, effective_date=future)
        confirm_employment_change(change, actor=self.hr_admin_1)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.CONFIRMED)  # not yet executed
        cancel_employment_change(change, actor=self.hr_admin_1)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.CANCELLED)
        self.assertTrue(RoleAssignment.objects.filter(employee=self.employee, revoked_at__isnull=True).exists())

    def test_cannot_cancel_an_executed_change(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION)
        confirm_employment_change(change, actor=self.hr_admin_1)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)
        with self.assertRaises(EmploymentChangeError):
            cancel_employment_change(change, actor=self.hr_admin_1)

    def test_cannot_execute_a_change_that_is_not_confirmed(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION)
        with self.assertRaises(EmploymentChangeError):
            execute_employment_change(change)


class SchedulingTests(ExitTestCase):
    def test_a_today_or_past_change_cascades_on_confirmation(self):
        change = self._propose(
            change_type=EmploymentChange.ChangeType.RESIGNATION, effective_date=timezone.localdate()
        )
        confirm_employment_change(change, actor=self.hr_admin_1)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)
        self.assertIsNotNone(change.executed_at)

    def test_a_future_dated_change_does_not_cascade_until_its_date(self):
        future = timezone.localdate() + timedelta(days=10)
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION, effective_date=future)
        confirm_employment_change(change, actor=self.hr_admin_1)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.CONFIRMED)
        self.assertTrue(RoleAssignment.objects.filter(employee=self.employee, revoked_at__isnull=True).exists())

        result = execute_due_employment_changes()
        self.assertEqual(result["executed"], 0)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.CONFIRMED)

    def test_the_scheduled_sweep_executes_a_change_whose_date_has_arrived(self):
        past = timezone.localdate() - timedelta(days=1)
        change = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION, effective_date=past)
        # Bypass confirm_employment_change's own immediate-execution path so
        # this genuinely exercises the scheduled sweep, not the confirm-time
        # shortcut -- create the row already CONFIRMED-but-unexecuted.
        change.state = EmploymentChange.State.CONFIRMED
        change.confirmed_by = self.hr_admin_1
        change.confirmed_at = timezone.now()
        change.save(update_fields=["state", "confirmed_by", "confirmed_at"])

        result = execute_due_employment_changes()
        self.assertEqual(result["executed"], 1)
        self.assertEqual(result["errors"], 0)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)

    def test_a_broken_execution_does_not_block_the_sweep_for_other_employees(self):
        """One employee's execution raising must not stop the sweep from
        reaching the next employee's due change (same isolation policy as
        data_quality.py/retention.py, applied at the sweep level)."""
        other = Employee.objects.hire(
            employee_number="E701", first_name="Also", last_name="Leaving", date_of_birth=date(1991, 1, 1),
            work_email="also.leaving@example.com", hire_date=date(2021, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        past = timezone.localdate() - timedelta(days=1)

        broken = self._propose(change_type=EmploymentChange.ChangeType.RESIGNATION, effective_date=past)
        broken.state = EmploymentChange.State.CONFIRMED
        broken.confirmed_by = self.hr_admin_1
        broken.confirmed_at = timezone.now()
        broken.save(update_fields=["state", "confirmed_by", "confirmed_at"])
        # Corrupt the row so apply_lifecycle_event fails inside execute():
        # effective_date not after valid_from triggers its own bare ValueError.
        broken.effective_date = self.employee.current_version.valid_from
        broken.save(update_fields=["effective_date"])

        healthy = propose_employment_change(
            employee=other, actor=self.hr_admin_1, change_type=EmploymentChange.ChangeType.RESIGNATION,
            effective_date=past, reason="Resigned.",
        )
        healthy.state = EmploymentChange.State.CONFIRMED
        healthy.confirmed_by = self.hr_admin_1
        healthy.confirmed_at = timezone.now()
        healthy.save(update_fields=["state", "confirmed_by", "confirmed_at"])

        result = execute_due_employment_changes()
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["executed"], 1)
        healthy.refresh_from_db()
        self.assertEqual(healthy.state, EmploymentChange.State.EXECUTED)
        broken.refresh_from_db()
        self.assertEqual(broken.state, EmploymentChange.State.CONFIRMED)  # unchanged, not corrupted further


class SuspensionTests(ExitTestCase):
    def test_suspension_revokes_roles_disables_login_and_suspends_biometrics(self):
        BiometricEnrollment.objects.create(employee=self.employee, descriptor=[0.1] * 128)

        change = self._propose(change_type=EmploymentChange.ChangeType.SUSPENSION)
        confirm_employment_change(change, actor=self.hr_admin_2)
        change.refresh_from_db()

        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)
        self.assertEqual(active_roles_for(self.employee).count(), 0)
        self.assertTrue(
            RoleAssignment.objects.filter(employee=self.employee, revoked_at__isnull=False).exists()
        )
        self.employee.user.refresh_from_db()
        self.assertFalse(self.employee.user.is_active)
        enrollment = BiometricEnrollment.objects.get(employee=self.employee)
        self.assertFalse(enrollment.active)

    def test_suspension_creates_no_employment_event_and_leaves_valid_to_null(self):
        """§2.1/§9's EEA2 guard -- the single most important shape in the
        spec. A suspended employee is still employed."""
        version_before = self.employee.current_version
        events_before = EmploymentEvent.objects.filter(employee=self.employee).count()

        change = self._propose(change_type=EmploymentChange.ChangeType.SUSPENSION)
        confirm_employment_change(change, actor=self.hr_admin_2)

        self.assertEqual(EmploymentEvent.objects.filter(employee=self.employee).count(), events_before)
        version_before.refresh_from_db()
        self.assertIsNone(version_before.valid_to)
        self.assertEqual(self.employee.versions.count(), 1)  # no new version opened either
        change.refresh_from_db()
        self.assertIsNone(change.resulting_event)

    def test_suspension_confirmation_requires_a_different_person(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.SUSPENSION)
        with self.assertRaises(EmploymentChangeError):
            confirm_employment_change(change, actor=self.hr_admin_1)


class LiftSuspensionTests(ExitTestCase):
    def _suspend(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.SUSPENSION)
        confirm_employment_change(change, actor=self.hr_admin_2)
        change.refresh_from_db()
        return change

    def test_lift_restores_exactly_the_roles_that_were_revoked_and_no_others(self):
        BiometricEnrollment.objects.create(employee=self.employee, descriptor=[0.1] * 128)
        suspension = self._suspend()
        self.assertEqual(active_roles_for(self.employee).count(), 0)

        lift = propose_employment_change(
            employee=self.employee, actor=self.hr_admin_1, change_type=EmploymentChange.ChangeType.LIFT_SUSPENSION,
            effective_date=timezone.localdate(), reason="Hearing cleared them.",
        )
        self.assertEqual(lift.lifts_suspension_id, suspension.id)
        confirm_employment_change(lift, actor=self.hr_admin_2)
        lift.refresh_from_db()

        self.assertEqual(lift.state, EmploymentChange.State.EXECUTED)
        restored_role_names = set(active_roles_for(self.employee).values_list("name", flat=True))
        self.assertEqual(restored_role_names, {self.role_employee.name, self.role_manager.name})
        self.employee.user.refresh_from_db()
        self.assertTrue(self.employee.user.is_active)
        enrollment = BiometricEnrollment.objects.get(employee=self.employee)
        self.assertTrue(enrollment.active)

        # The restored grants are NEW rows, not the old ones un-revoked
        # (spec §6.2) -- the old rows stay revoked, present, and auditable.
        self.assertEqual(
            RoleAssignment.objects.filter(employee=self.employee, revoked_at__isnull=False).count(), 2
        )
        self.assertEqual(
            RoleAssignment.objects.filter(employee=self.employee, revoked_at__isnull=True).count(), 2
        )

    def test_lift_does_not_restore_a_role_that_was_granted_again_in_the_meantime(self):
        suspension = self._suspend()
        RoleAssignment.objects.create(employee=self.employee, role=self.role_employee, granted_by=self.hr_admin_1)

        lift = propose_employment_change(
            employee=self.employee, actor=self.hr_admin_1, change_type=EmploymentChange.ChangeType.LIFT_SUSPENSION,
            effective_date=timezone.localdate(), reason="Cleared.",
        )
        confirm_employment_change(lift, actor=self.hr_admin_2)

        # Only one active 'employee' assignment -- the DB constraint would
        # have raised IntegrityError had the lift tried to create a second.
        self.assertEqual(
            RoleAssignment.objects.filter(
                employee=self.employee, role=self.role_employee, revoked_at__isnull=True
            ).count(),
            1,
        )
        self.assertEqual(active_roles_for(self.employee).filter(name=self.role_manager.name).count(), 1)

    def test_propose_lift_with_no_active_suspension_is_rejected(self):
        with self.assertRaises(EmploymentChangeError):
            self._propose(change_type=EmploymentChange.ChangeType.LIFT_SUSPENSION)

    def test_a_second_suspend_lift_cycle_targets_the_newer_suspension(self):
        first_suspension = self._suspend()
        first_lift = propose_employment_change(
            employee=self.employee, actor=self.hr_admin_1, change_type=EmploymentChange.ChangeType.LIFT_SUSPENSION,
            effective_date=timezone.localdate(), reason="Cleared once.",
        )
        confirm_employment_change(first_lift, actor=self.hr_admin_2)

        second_suspension = self._suspend()
        self.assertNotEqual(second_suspension.id, first_suspension.id)
        second_lift = propose_employment_change(
            employee=self.employee, actor=self.hr_admin_1, change_type=EmploymentChange.ChangeType.LIFT_SUSPENSION,
            effective_date=timezone.localdate(), reason="Cleared again.",
        )
        self.assertEqual(second_lift.lifts_suspension_id, second_suspension.id)


class DismissalTests(ExitTestCase):
    def test_dismissal_summary_forces_effective_date_to_today(self):
        change = self._propose(
            change_type=EmploymentChange.ChangeType.DISMISSAL_SUMMARY,
            effective_date=timezone.localdate() + timedelta(days=30),
        )
        self.assertEqual(change.effective_date, timezone.localdate())

    def test_dismissal_summary_full_cascade(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.DISMISSAL_SUMMARY)
        confirm_employment_change(change, actor=self.hr_admin_2)
        change.refresh_from_db()

        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)
        self.assertEqual(active_roles_for(self.employee).count(), 0)
        self.employee.user.refresh_from_db()
        self.assertFalse(self.employee.user.is_active)
        self.assertIsNotNone(change.resulting_event)
        self.assertEqual(
            change.resulting_event.termination_reason, EmploymentEvent.TerminationReason.DISMISSAL_MISCONDUCT
        )
        current_version = self.employee.versions.filter(valid_to__isnull=True).first()
        self.assertIsNone(current_version)  # dismissal closes the version and opens none

    def test_dismissal_summary_confirmation_requires_a_different_person(self):
        change = self._propose(change_type=EmploymentChange.ChangeType.DISMISSAL_SUMMARY)
        with self.assertRaises(EmploymentChangeError):
            confirm_employment_change(change, actor=self.hr_admin_1)

    def test_termination_reason_mapping_for_each_ending_type(self):
        mapping = {
            EmploymentChange.ChangeType.DISMISSAL_MISCONDUCT: EmploymentEvent.TerminationReason.DISMISSAL_MISCONDUCT,
            EmploymentChange.ChangeType.DISMISSAL_INCAPACITY: EmploymentEvent.TerminationReason.DISMISSAL_INCAPACITY,
            EmploymentChange.ChangeType.OPERATIONAL_REQUIREMENTS: EmploymentEvent.TerminationReason.OPERATIONAL_REQUIREMENTS,
            EmploymentChange.ChangeType.RESIGNATION: EmploymentEvent.TerminationReason.RESIGNATION,
            EmploymentChange.ChangeType.RETIREMENT: EmploymentEvent.TerminationReason.RETIREMENT,
            EmploymentChange.ChangeType.DEATH: EmploymentEvent.TerminationReason.DEATH,
            EmploymentChange.ChangeType.CONTRACT_END: EmploymentEvent.TerminationReason.CONTRACT_END,
        }
        for index, (change_type, expected_reason) in enumerate(mapping.items()):
            with self.subTest(change_type=change_type):
                leaver = Employee.objects.hire(
                    employee_number=f"E80{index}", first_name="Leaver", last_name=str(index),
                    date_of_birth=date(1990, 1, 1), work_email=f"leaver{index}@example.com",
                    hire_date=date(2020, 1, 1), department=self.dept, occupational_level=self.level,
                    job_grade=self.grade, location=self.location,
                )
                change = propose_employment_change(
                    employee=leaver, actor=self.hr_admin_1, change_type=change_type,
                    effective_date=timezone.localdate(), reason="Reason.",
                )
                confirmer = self.hr_admin_2 if change_type in EmploymentChange.TIERED_CHANGE_TYPES else self.hr_admin_1
                confirm_employment_change(change, actor=confirmer)
                change.refresh_from_db()
                self.assertEqual(change.resulting_event.termination_reason, expected_reason)


class HistoryNonDestructionTests(ExitTestCase):
    """Spec §6.3/§9: the cascade withdraws access, it must never delete
    history. After a summary dismissal specifically -- the most abrupt
    path, most likely to be litigated -- everything must still be there."""

    def test_summary_dismissal_leaves_every_record_intact(self):
        # A prior version change, so there's a real chain to check.
        self.employee.apply_lifecycle_event(
            event_type=EmploymentEvent.EventType.PROMOTION, effective_date=date(2022, 1, 1),
            job_title="Senior Something",
        )
        version_count_before = self.employee.versions.count()
        self.assertEqual(version_count_before, 2)

        BiometricEnrollment.objects.create(employee=self.employee, descriptor=[0.2] * 128)
        liveness_check = LivenessCheck.objects.create(
            employee=self.employee, outcome=LivenessCheck.Outcome.MATCH, match_distance=0.1,
        )
        role_assignment_ids = list(
            RoleAssignment.objects.filter(employee=self.employee, revoked_at__isnull=True).values_list(
                "id", flat=True
            )
        )
        self.assertEqual(len(role_assignment_ids), 2)

        change = self._propose(
            change_type=EmploymentChange.ChangeType.DISMISSAL_SUMMARY, reason="Gross misconduct — theft."
        )
        confirm_employment_change(change, actor=self.hr_admin_2)
        change.refresh_from_db()

        # 1. The full EmployeeVersion chain survives, closed not deleted.
        self.assertEqual(self.employee.versions.count(), version_count_before + 0)
        # apply_lifecycle_event on TERMINATION closes the current version
        # and opens none, so the count doesn't grow -- but nothing shrank
        # either, and every version is still readable:
        for version in self.employee.versions.all():
            self.assertIsNotNone(version.pk)
        latest = self.employee.versions.order_by("-valid_from").first()
        self.assertIsNotNone(latest.valid_to)  # closed

        # 2. An EmploymentEvent exists carrying the termination reason.
        self.assertIsNotNone(change.resulting_event)
        self.assertEqual(change.resulting_event.event_type, EmploymentEvent.EventType.TERMINATION)
        self.assertEqual(
            change.resulting_event.termination_reason, EmploymentEvent.TerminationReason.DISMISSAL_MISCONDUCT
        )

        # 3. The EmploymentChange still names its proposer, confirmer, reason.
        self.assertEqual(change.proposed_by, self.hr_admin_1)
        self.assertEqual(change.confirmed_by, self.hr_admin_2)
        self.assertEqual(change.reason, "Gross misconduct — theft.")

        # 4. Revoked RoleAssignment rows still exist, revoked not deleted.
        for assignment_id in role_assignment_ids:
            assignment = RoleAssignment.objects.get(id=assignment_id)
            self.assertIsNotNone(assignment.revoked_at)

        # 5. LivenessCheck history survives untouched.
        self.assertTrue(LivenessCheck.objects.filter(id=liveness_check.id).exists())
        liveness_check.refresh_from_db()
        self.assertEqual(liveness_check.outcome, LivenessCheck.Outcome.MATCH)


class SecurityEndToEndTests(ExitTestCase):
    """Spec §9's headline regression guard for §1.1's hole: a terminated
    employee genuinely loses access, not just a database flag nobody reads."""

    def test_exited_employee_loses_role_gated_endpoint_access(self):
        client = APIClient()
        client.force_authenticate(user=self.employee.user)
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="hr_admin"))
        response = client.get("/api/v1/applicants/")
        self.assertEqual(response.status_code, 200)

        change = self._propose(change_type=EmploymentChange.ChangeType.DISMISSAL_SUMMARY)
        confirm_employment_change(change, actor=self.hr_admin_2)

        response = client.get("/api/v1/applicants/")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(active_roles_for(self.employee).exists())

    def test_exited_employee_cannot_log_in(self):
        client = APIClient()
        response = client.post(
            "/api/v1/auth/login/", {"username": "departing", "password": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        client.post("/api/v1/auth/logout/")

        change = self._propose(change_type=EmploymentChange.ChangeType.DISMISSAL_SUMMARY)
        confirm_employment_change(change, actor=self.hr_admin_2)

        response = client.post(
            "/api/v1/auth/login/", {"username": "departing", "password": "x"}, format="json"
        )
        self.assertEqual(response.status_code, 401)


class HandlerFailureIsolationTests(ExitTestCase):
    def test_a_failing_exit_handler_does_not_abort_the_exit_or_block_siblings(self):
        def _boom(employee):
            raise RuntimeError("simulated handler failure")

        with access_cascade.temporary_exit_handler("test.Broken", _boom):
            change = self._propose(change_type=EmploymentChange.ChangeType.DISMISSAL_SUMMARY)
            confirm_employment_change(change, actor=self.hr_admin_2)

        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)
        self.assertEqual(active_roles_for(self.employee).count(), 0)
        self.employee.user.refresh_from_db()
        self.assertFalse(self.employee.user.is_active)
        self.assertIsNotNone(change.resulting_event)


class NoUserAccountTests(ExitTestCase):
    def test_an_employee_with_no_user_account_does_not_break_the_cascade(self):
        no_login_employee = Employee.objects.hire(
            employee_number="E900X", first_name="No", last_name="Login", date_of_birth=date(1990, 1, 1),
            work_email="no.login@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        RoleAssignment.objects.create(employee=no_login_employee, role=Role.objects.get(name="employee"))
        self.assertIsNone(no_login_employee.user)

        change = propose_employment_change(
            employee=no_login_employee, actor=self.hr_admin_1, change_type=EmploymentChange.ChangeType.RESIGNATION,
            effective_date=timezone.localdate(), reason="Resigned.",
        )
        confirm_employment_change(change, actor=self.hr_admin_1)
        change.refresh_from_db()
        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)
        self.assertEqual(active_roles_for(no_login_employee).count(), 0)


class AuditLoggingTests(ExitTestCase):
    def test_every_cascade_step_writes_an_audit_log_entry(self):
        BiometricEnrollment.objects.create(employee=self.employee, descriptor=[0.1] * 128)
        entries_before = AuditLogEntry.objects.count()

        change = self._propose(change_type=EmploymentChange.ChangeType.DISMISSAL_SUMMARY)
        confirm_employment_change(change, actor=self.hr_admin_2)

        new_entries = AuditLogEntry.objects.filter(id__gt=0).order_by("id")[entries_before:]
        entity_types = {e.entity_type for e in new_entries}
        self.assertIn("rbac_audit.RoleAssignment", entity_types)
        self.assertIn("auth.User", entity_types)
        self.assertIn("identity_verification.BiometricEnrollment", entity_types)
        self.assertIn("core_hr.EmploymentEvent", entity_types)


class RetentionRuleSeedTests(TestCase):
    def test_employment_event_and_employment_change_are_seeded_as_retain(self):
        for entity_type in ("core_hr.EmploymentEvent", "core_hr.EmploymentChange"):
            rule = RetentionRule.objects.get(entity_type=entity_type)
            self.assertEqual(rule.action, RetentionRule.Action.RETAIN)
            self.assertTrue(rule.active)


class ContractLapseRoutesThroughCascadeTests(ExitTestCase):
    """C1 part 2's `let_lapse` closes employment for an expiring fixed-term
    contract. It originally called `apply_lifecycle_event` directly, so it
    closed the employment while leaving roles, login and biometric
    enrolment fully live -- the exact hole this cascade exists to close,
    open for an entire class of leavers. It now routes through
    `exits.record_executed_exit`."""

    def setUp(self):
        super().setUp()
        version = self.employee.current_version
        version.employment_status = EmployeeVersion.EmploymentStatus.FIXED_TERM
        version.contract_end_date = timezone.localdate() + timedelta(days=30)
        version.save(update_fields=["employment_status", "contract_end_date"])
        self.version = self.employee.current_version
        from establishment.models import Position

        self.vacant_position = Position.objects.create(
            post_number="P-CONV-700", title="Converted Role", department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            status=Position.Status.APPROVED,
        )

    def _decide(self, action, **kwargs):
        from .contracts import decide_contract_action

        return decide_contract_action(self.version, actor=self.hr_admin_1, action=action, **kwargs)

    def test_let_lapse_withdraws_access(self):
        self.assertEqual(active_roles_for(self.employee).count(), 2)
        self._decide(ContractRenewalDecision.Action.LET_LAPSE)

        self.assertEqual(active_roles_for(self.employee).count(), 0)
        self.employee.user.refresh_from_db()
        self.assertFalse(self.employee.user.is_active)

    def test_let_lapse_records_an_employment_change_for_provenance(self):
        self._decide(ContractRenewalDecision.Action.LET_LAPSE)
        change = EmploymentChange.objects.get(employee=self.employee)
        self.assertEqual(change.change_type, EmploymentChange.ChangeType.CONTRACT_END)
        self.assertEqual(change.state, EmploymentChange.State.EXECUTED)
        # The reason is required on EmploymentChange and this workflow only
        # collects an optional comment, so it must still name the cause.
        self.assertIn("lapsed", change.reason.lower())
        self.assertEqual(change.revoked_role_assignments.count(), 2)

    def test_let_lapse_still_preserves_history(self):
        self._decide(ContractRenewalDecision.Action.LET_LAPSE)
        self.version.refresh_from_db()
        self.assertIsNotNone(self.version.valid_to)  # closed, not deleted
        event = EmploymentEvent.objects.get(from_version=self.version)
        self.assertEqual(event.termination_reason, EmploymentEvent.TerminationReason.CONTRACT_END)
        # Revoked, not deleted -- "what access did they hold" stays answerable.
        self.assertEqual(
            RoleAssignment.objects.filter(employee=self.employee, revoked_at__isnull=False).count(), 2
        )

    def test_renew_leaves_access_untouched(self):
        self._decide(
            ContractRenewalDecision.Action.RENEW,
            end_date=timezone.localdate() + timedelta(days=400),
        )
        self.assertEqual(active_roles_for(self.employee).count(), 2)
        self.employee.user.refresh_from_db()
        self.assertTrue(self.employee.user.is_active)
        self.assertFalse(EmploymentChange.objects.filter(employee=self.employee).exists())

    def test_convert_permanent_leaves_access_untouched(self):
        self._decide(ContractRenewalDecision.Action.CONVERT_PERMANENT, position_id=self.vacant_position.id)
        self.assertEqual(active_roles_for(self.employee).count(), 2)
        self.employee.user.refresh_from_db()
        self.assertTrue(self.employee.user.is_active)
        self.assertFalse(EmploymentChange.objects.filter(employee=self.employee).exists())

    def test_open_employment_change_blocks_the_lapse_with_a_clear_message(self):
        """Someone mid-decision about this person (a suspension pending a
        hearing, say) is a genuine conflict for a human to resolve. It must
        surface as a clean domain error, not as an IntegrityError from the
        one-open-change constraint, and not wearing the generic
        'already changed today' message the ValueError handler applies."""
        from .contracts import ContractDecisionError

        self._propose(change_type=EmploymentChange.ChangeType.SUSPENSION)
        with self.assertRaises(ContractDecisionError) as ctx:
            self._decide(ContractRenewalDecision.Action.LET_LAPSE)
        message = str(ctx.exception).lower()
        self.assertIn("employment change", message)
        # The point of the dedicated EmploymentChangeError clause: without
        # it the generic ValueError handler swallows this and substitutes an
        # unrelated explanation, sending HR to look at the wrong problem.
        self.assertNotIn("already changed today", message)
        # And the lapse genuinely did not happen.
        self.version.refresh_from_db()
        self.assertIsNone(self.version.valid_to)
