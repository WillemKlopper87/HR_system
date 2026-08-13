from __future__ import annotations

import json
from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rbac_audit.consent import record_consent
from rbac_audit.models import ConsentRecord

from . import webhooks
from .adapters.registry import get_active_adapter
from .adapters.sandbox import SandboxAdapter
from .models import AssessmentAssignment, AssessmentResult, ProviderConfig
from .services import (
    ConsentRequiredError,
    WebhookProcessingError,
    assign_assessment,
    process_webhook_result,
    simulate_provider_completion,
)


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


def _hire(employee_number, *, dept, level, grade, location):
    return Employee.objects.hire(
        employee_number=employee_number, first_name="Alex", last_name="Employee", date_of_birth=date(1990, 1, 1),
        work_email=f"{employee_number.lower()}@example.com", hire_date=date(2020, 1, 1),
        department=dept, occupational_level=level, job_grade=grade, location=location,
    )


class AssessmentAssignmentModelTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)

    def test_exactly_one_subject_constraint_rejects_neither(self):
        with self.assertRaises(IntegrityError):
            AssessmentAssignment.objects.create(assessment_type=AssessmentAssignment.AssessmentType.COGNITIVE)

    def test_exactly_one_subject_constraint_rejects_both(self):
        with self.assertRaises(IntegrityError):
            AssessmentAssignment.objects.create(
                employee=self.employee, applicant_id=1, assessment_type=AssessmentAssignment.AssessmentType.COGNITIVE
            )

    def test_employee_only_subject_is_valid(self):
        assignment = AssessmentAssignment.objects.create(
            employee=self.employee, assessment_type=AssessmentAssignment.AssessmentType.COGNITIVE
        )
        self.assertIsNone(assignment.applicant_id)


class ProviderConfigModelTests(TestCase):
    def test_only_one_active_provider_allowed(self):
        ProviderConfig.objects.create(provider_key="sandbox", display_name="Sandbox", active=True)
        with self.assertRaises(IntegrityError):
            ProviderConfig.objects.create(provider_key="other", display_name="Other", active=True)

    def test_multiple_inactive_providers_allowed(self):
        ProviderConfig.objects.create(provider_key="sandbox", display_name="Sandbox", active=False)
        ProviderConfig.objects.create(provider_key="other", display_name="Other", active=False)
        self.assertEqual(ProviderConfig.objects.count(), 2)


class AdapterRegistryTests(TestCase):
    def test_falls_back_to_sandbox_when_no_config_row_exists(self):
        adapter = get_active_adapter()
        self.assertIsInstance(adapter, SandboxAdapter)

    def test_falls_back_to_sandbox_when_no_row_is_active(self):
        ProviderConfig.objects.create(provider_key="sandbox", display_name="Sandbox", active=False)
        adapter = get_active_adapter()
        self.assertIsInstance(adapter, SandboxAdapter)

    def test_resolves_the_active_row(self):
        ProviderConfig.objects.create(provider_key="sandbox", display_name="Sandbox", active=True)
        adapter = get_active_adapter()
        self.assertEqual(adapter.provider_key, "sandbox")


class WebhookSignatureTests(TestCase):
    def setUp(self):
        self.body = json.dumps({"provider_reference": "ref-1", "status": "completed"}).encode()
        self.timestamp = int(timezone.now().timestamp())
        self.signature = webhooks.sign_payload(self.body, timestamp=self.timestamp)

    def test_valid_signature_passes(self):
        webhooks.verify_signature(self.body, signature=self.signature, timestamp=str(self.timestamp))

    def test_missing_signature_is_rejected(self):
        with self.assertRaises(webhooks.WebhookVerificationError):
            webhooks.verify_signature(self.body, signature="", timestamp=str(self.timestamp))

    def test_wrong_signature_is_rejected(self):
        with self.assertRaises(webhooks.WebhookVerificationError):
            webhooks.verify_signature(self.body, signature="0" * 64, timestamp=str(self.timestamp))

    def test_tampered_body_is_rejected(self):
        tampered = json.dumps({"provider_reference": "ref-1", "status": "expired"}).encode()
        with self.assertRaises(webhooks.WebhookVerificationError):
            webhooks.verify_signature(tampered, signature=self.signature, timestamp=str(self.timestamp))

    def test_stale_timestamp_is_rejected(self):
        stale = self.timestamp - webhooks.REPLAY_WINDOW_SECONDS - 60
        stale_signature = webhooks.sign_payload(self.body, timestamp=stale)
        with self.assertRaises(webhooks.WebhookVerificationError):
            webhooks.verify_signature(self.body, signature=stale_signature, timestamp=str(stale))

    def test_non_integer_timestamp_is_rejected(self):
        with self.assertRaises(webhooks.WebhookVerificationError):
            webhooks.verify_signature(self.body, signature=self.signature, timestamp="not-a-number")


class AssignAssessmentServiceTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)

    def test_requires_exactly_one_subject(self):
        with self.assertRaises(ValueError):
            assign_assessment(assessment_type=AssessmentAssignment.AssessmentType.COGNITIVE)

    def test_blocks_assignment_without_consent(self):
        with self.assertRaises(ConsentRequiredError):
            assign_assessment(employee=self.employee, assessment_type=AssessmentAssignment.AssessmentType.COGNITIVE)

    def test_succeeds_once_consent_is_recorded(self):
        record_consent(
            employee=self.employee, purpose=ConsentRecord.Purpose.ASSESSMENT,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )
        assignment = assign_assessment(employee=self.employee, assessment_type=AssessmentAssignment.AssessmentType.COGNITIVE)
        self.assertEqual(assignment.provider_key, "sandbox")
        self.assertTrue(assignment.provider_reference)
        self.assertTrue(assignment.access_url)
        self.assertEqual(assignment.status, AssessmentAssignment.Status.ASSIGNED)

    def test_withdrawn_consent_blocks_a_new_assignment(self):
        consent = record_consent(
            employee=self.employee, purpose=ConsentRecord.Purpose.ASSESSMENT,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )
        consent.withdrawn_at = timezone.now()
        consent.save(update_fields=["withdrawn_at"])
        with self.assertRaises(ConsentRequiredError):
            assign_assessment(employee=self.employee, assessment_type=AssessmentAssignment.AssessmentType.COGNITIVE)


class ProcessWebhookResultServiceTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = _hire("E001", dept=self.dept, level=self.level, grade=self.grade, location=self.location)
        record_consent(
            employee=self.employee, purpose=ConsentRecord.Purpose.ASSESSMENT,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )
        self.assignment = assign_assessment(
            employee=self.employee, assessment_type=AssessmentAssignment.AssessmentType.COGNITIVE
        )

    def test_unknown_provider_reference_raises(self):
        with self.assertRaises(WebhookProcessingError):
            process_webhook_result(provider_reference="does-not-exist", status="completed")

    def test_unknown_status_raises(self):
        with self.assertRaises(WebhookProcessingError):
            process_webhook_result(provider_reference=self.assignment.provider_reference, status="bogus")

    def test_completion_creates_a_result_and_stamps_completed_at(self):
        updated = process_webhook_result(
            provider_reference=self.assignment.provider_reference, status=AssessmentAssignment.Status.COMPLETED,
            raw_score="80", summary="Great", detail={"a": 1},
        )
        self.assertEqual(updated.status, AssessmentAssignment.Status.COMPLETED)
        self.assertIsNotNone(updated.completed_at)
        result = AssessmentResult.objects.get(assignment=updated)
        self.assertEqual(result.raw_score, "80")
        self.assertEqual(result.detail, {"a": 1})

    def test_non_completion_status_does_not_create_a_result(self):
        process_webhook_result(provider_reference=self.assignment.provider_reference, status=AssessmentAssignment.Status.IN_PROGRESS)
        self.assertFalse(AssessmentResult.objects.filter(assignment=self.assignment).exists())

    def test_reprocessing_the_same_reference_is_idempotent_not_duplicated(self):
        process_webhook_result(
            provider_reference=self.assignment.provider_reference, status=AssessmentAssignment.Status.COMPLETED,
            raw_score="80", summary="First",
        )
        process_webhook_result(
            provider_reference=self.assignment.provider_reference, status=AssessmentAssignment.Status.COMPLETED,
            raw_score="90", summary="Retried delivery",
        )
        self.assertEqual(AssessmentResult.objects.filter(assignment=self.assignment).count(), 1)
        result = AssessmentResult.objects.get(assignment=self.assignment)
        self.assertEqual(result.raw_score, "90")

    def test_simulate_provider_completion_exercises_the_real_pipeline(self):
        updated = simulate_provider_completion(self.assignment)
        self.assertEqual(updated.status, AssessmentAssignment.Status.COMPLETED)
        self.assertTrue(hasattr(updated, "result"))
        self.assertTrue(updated.result.summary)
