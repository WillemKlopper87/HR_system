"""Calibration/moderation (C6, design spec 2026-08-25-performance-
calibration-360-design.md). Reuses ReviewTestCase's fixture (PC-2's test
file) and a `_final_signed` helper identical to test_pc3.py's own.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from core_hr.models import Department, Employee
from rbac_audit.models import AuditLogEntry, Role, RoleAssignment

from .data_quality import missing_calibration_handler
from .models import PerformanceAgreement, PerformancePeriod, PeriodPhase
from .services import AgreementWorkflowError, sign_agreement
from .services.calibration import close_session, eligible_agreements, open_session, record_calibration_outcome
from .test_agreements import PASSWORD
from .test_reviews import ReviewTestCase

User = get_user_model()


class CalibrationTestCase(ReviewTestCase):
    def _final_signed(self, **kwargs):
        agreement = self._agreed(**kwargs)
        self._open_final(agreement)
        self._rate_all(agreement, 4)
        sign_agreement(agreement, actor=agreement.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        return agreement

    def _hire_in(self, number, first, last, username, department, manager=None):
        return Employee.objects.hire(
            employee_number=number, first_name=first, last_name=last, date_of_birth=date(1990, 1, 1),
            work_email=f"{username}@sentech.example.com", hire_date=date(2020, 1, 1), department=department,
            occupational_level=self.level, job_grade=self.grade, location=self.location, manager=manager,
            user=User.objects.create_user(username=username, password=PASSWORD),
        )


class EligibilityTests(CalibrationTestCase):
    def test_only_final_signed_or_archived_agreements_are_eligible(self):
        finished = self._final_signed()
        still_agreed = self._agreed(employee=self._hire("E050", "Still", "Agreed", "stillagreed", manager=self.head))
        session = open_session(period=self.period, actor=self.hr_admin)
        candidates = eligible_agreements(session)
        self.assertIn(finished, candidates)
        self.assertNotIn(still_agreed, candidates)

    def test_department_scoping(self):
        other_dept = Department.objects.create(name="Sales", code="SAL")
        in_dept = self._final_signed()
        outsider = self._hire_in("E051", "Out", "Sider", "outsider1", other_dept, manager=self.head)
        out_of_dept = self._final_signed(employee=outsider)

        scoped = open_session(period=self.period, department=self.dept, actor=self.hr_admin)
        scoped_candidates = eligible_agreements(scoped)
        self.assertIn(in_dept, scoped_candidates)
        self.assertNotIn(out_of_dept, scoped_candidates)

        org_wide = open_session(period=self.period, actor=self.hr_admin)
        org_wide_candidates = eligible_agreements(org_wide)
        self.assertIn(in_dept, org_wide_candidates)
        self.assertIn(out_of_dept, org_wide_candidates)


class RecordOutcomeTests(CalibrationTestCase):
    def setUp(self):
        super().setUp()
        self.agreement = self._final_signed()
        self.session = open_session(period=self.period, department=self.dept, actor=self.hr_admin)

    def test_no_change_outcome_leaves_final_score_untouched_but_is_recorded(self):
        before = self.agreement.final_score
        adjustment = record_calibration_outcome(
            self.session, self.agreement, actor=self.hr_admin, reason="Consistent with the rest of the cohort.",
        )
        self.agreement.refresh_from_db()
        self.assertEqual(self.agreement.final_score, before)
        self.assertIsNone(adjustment.new_score)
        self.assertEqual(adjustment.previous_score, before)
        self.assertEqual(adjustment.adjusted_by, self.hr_admin)

    def test_adjustment_changes_final_score_and_is_never_silent(self):
        before = self.agreement.final_score
        history_count_before = self.agreement.history.count()
        adjustment = record_calibration_outcome(
            self.session, self.agreement, actor=self.hr_admin,
            reason="Head over-rated relative to the department distribution.", new_score=Decimal("2.50"),
        )
        self.agreement.refresh_from_db()
        self.assertEqual(self.agreement.final_score, Decimal("2.50"))
        self.assertTrue(self.agreement.hr_attention)  # below the 3.00 default threshold
        self.assertIn("calibration-adjusted", self.agreement.hr_attention_reason)
        self.assertEqual(adjustment.previous_score, before)
        self.assertEqual(adjustment.new_score, Decimal("2.50"))
        # Three independent trails, per spec §2.4: the CalibrationAdjustment
        # row itself, PerformanceAgreement.history (existing simple_history),
        # and the audit log.
        self.assertEqual(self.agreement.history.count(), history_count_before + 1)
        self.assertTrue(
            AuditLogEntry.objects.filter(
                entity_type="performance.PerformanceAgreement", entity_id=str(self.agreement.pk),
                fields_touched__icontains="calibration session",
            ).exists()
        )

    def test_original_signatures_and_documents_are_untouched(self):
        signature_count = self.agreement.signatures.count()
        document_count = self.agreement.documents.count()
        record_calibration_outcome(
            self.session, self.agreement, actor=self.hr_admin, reason="Adjusted for consistency.",
            new_score=Decimal("2.00"),
        )
        self.agreement.refresh_from_db()
        self.assertEqual(self.agreement.signatures.count(), signature_count)
        self.assertEqual(self.agreement.documents.count(), document_count)
        # Still AGREED/FINAL_SIGNED, never bounced back to DRAFT the way
        # amend_agreement would (no re-signature, spec §2.4).
        self.assertEqual(self.agreement.status, PerformanceAgreement.Status.FINAL_SIGNED)
        self.assertEqual(self.agreement.revision, 1)

    def test_reason_is_required_even_for_no_change(self):
        with self.assertRaises(AgreementWorkflowError):
            record_calibration_outcome(self.session, self.agreement, actor=self.hr_admin, reason="   ")

    def test_cannot_record_twice_for_the_same_agreement_in_one_session(self):
        record_calibration_outcome(self.session, self.agreement, actor=self.hr_admin, reason="First pass.")
        with self.assertRaises(AgreementWorkflowError):
            record_calibration_outcome(self.session, self.agreement, actor=self.hr_admin, reason="Second pass.")

    def test_ineligible_agreement_is_refused(self):
        still_agreed = self._agreed(employee=self._hire("E052", "Still", "Agreed", "stillagreed2", manager=self.head))
        with self.assertRaises(AgreementWorkflowError):
            record_calibration_outcome(self.session, still_agreed, actor=self.hr_admin, reason="Too early.")

    def test_cannot_record_outcome_on_a_completed_session(self):
        close_session(self.session, actor=self.hr_admin)
        with self.assertRaises(AgreementWorkflowError):
            record_calibration_outcome(self.session, self.agreement, actor=self.hr_admin, reason="Too late.")

    def test_close_session_is_idempotent_guarded(self):
        close_session(self.session, actor=self.hr_admin)
        with self.assertRaises(AgreementWorkflowError):
            close_session(self.session, actor=self.hr_admin)


class ApiPermissionTests(CalibrationTestCase):
    def setUp(self):
        super().setUp()
        self.agreement = self._final_signed()

    def test_only_hr_admin_can_open_a_session(self):
        self._login(self.head)
        blocked = self.client.post("/api/v1/calibration-sessions/", {"period": self.period.id}, format="json")
        self.assertEqual(blocked.status_code, 403)

        self._login(self.hr_admin)
        ok = self.client.post("/api/v1/calibration-sessions/", {"period": self.period.id}, format="json")
        self.assertEqual(ok.status_code, 201, ok.data)

    def test_only_hr_admin_and_auditor_can_read_sessions(self):
        session = open_session(period=self.period, actor=self.hr_admin)
        auditor = self._hire("AUD1", "Ivy", "Auditor", "ivyaud1")
        RoleAssignment.objects.create(employee=auditor, role=Role.objects.get(name="auditor"))

        for viewer, allowed in ((self.head, False), (self.employee, False), (auditor, True), (self.hr_admin, True)):
            self._login(viewer)
            response = self.client.get(f"/api/v1/calibration-sessions/{session.id}/")
            self.assertEqual(response.status_code, 200 if allowed else 403, viewer.employee_number)

    def test_record_outcome_action_requires_hr_admin(self):
        session = open_session(period=self.period, actor=self.hr_admin)
        self._login(self.head)
        blocked = self.client.post(
            f"/api/v1/calibration-sessions/{session.id}/record-outcome/",
            {"agreement": self.agreement.id, "reason": "Trying anyway."}, format="json",
        )
        self.assertEqual(blocked.status_code, 403)

        self._login(self.hr_admin)
        ok = self.client.post(
            f"/api/v1/calibration-sessions/{session.id}/record-outcome/",
            {"agreement": self.agreement.id, "reason": "Reviewed, no change.", "new_score": "3.60"}, format="json",
        )
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(len(ok.data["adjustments"]), 1)

    def test_candidates_action_excludes_already_recorded(self):
        session = open_session(period=self.period, actor=self.hr_admin)
        self._login(self.hr_admin)
        before = self.client.get(f"/api/v1/calibration-sessions/{session.id}/candidates/")
        self.assertEqual(before.status_code, 200)
        self.assertEqual(len(before.data), 1)

        record_calibration_outcome(session, self.agreement, actor=self.hr_admin, reason="Reviewed.")
        after = self.client.get(f"/api/v1/calibration-sessions/{session.id}/candidates/")
        self.assertEqual(len(after.data), 0)

    def test_agreement_read_carries_its_own_calibration_adjustment_to_its_subject(self):
        session = open_session(period=self.period, actor=self.hr_admin)
        record_calibration_outcome(
            session, self.agreement, actor=self.hr_admin, reason="Aligned to department norm.",
            new_score=Decimal("3.10"),
        )
        self._login(self.employee)
        response = self.client.get(f"/api/v1/performance-agreements/{self.agreement.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["calibration_adjustments"]), 1)
        self.assertEqual(response.data["calibration_adjustments"][0]["new_score"], "3.10")

    def test_unrelated_employee_cannot_see_the_session_at_all(self):
        session = open_session(period=self.period, actor=self.hr_admin)
        self._login(self.other)
        response = self.client.get(f"/api/v1/calibration-sessions/{session.id}/")
        self.assertEqual(response.status_code, 403)


class DataQualityTests(CalibrationTestCase):
    def test_flags_final_signed_agreement_once_final_phase_is_overdue_with_no_session(self):
        agreement = self._final_signed()
        self.period.status = PerformancePeriod.Status.FINAL
        self.period.save(update_fields=["status"])
        final_phase = self.period.phases.get(stage=PeriodPhase.Stage.FINAL)
        final_phase.due_on = date(2020, 1, 1)
        final_phase.save(update_fields=["due_on"])

        flagged = list(missing_calibration_handler())
        self.assertIn(agreement.employee, [emp for emp, _ in flagged])

    def test_no_flag_once_any_session_exists_for_the_period(self):
        agreement = self._final_signed()
        self.period.status = PerformancePeriod.Status.FINAL
        self.period.save(update_fields=["status"])
        final_phase = self.period.phases.get(stage=PeriodPhase.Stage.FINAL)
        final_phase.due_on = date(2020, 1, 1)
        final_phase.save(update_fields=["due_on"])
        open_session(period=self.period, actor=self.hr_admin)  # even empty, this counts as "looked at"

        flagged = list(missing_calibration_handler())
        self.assertNotIn(agreement.employee, [emp for emp, _ in flagged])

    def test_no_flag_while_still_within_the_final_phase_window(self):
        agreement = self._final_signed()
        self.period.status = PerformancePeriod.Status.FINAL
        self.period.save(update_fields=["status"])
        # Fixture's FINAL due_on is 2027-04-30, in the future relative to "today".
        flagged = list(missing_calibration_handler())
        self.assertNotIn(agreement.employee, [emp for emp, _ in flagged])
