from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.test import TestCase

from . import subject_export


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG-SE")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="GSE1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HOSE", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class SubjectExportRegistryTests(TestCase):
    def test_register_and_lookup(self):
        def handler(employee):
            return subject_export.DomainExportResult(status=subject_export.DomainStatus.NO_RECORDS)

        with subject_export.temporary_handler("demo.Thing", handler):
            self.assertIn("demo.Thing", subject_export.registered_domains())
            self.assertIn("demo.Thing", subject_export.required_domains())
        self.assertNotIn("demo.Thing", subject_export.registered_domains())

    def test_required_false_keeps_the_domain_registered_but_not_required(self):
        def handler(employee):
            return subject_export.DomainExportResult(status=subject_export.DomainStatus.NO_RECORDS)

        with subject_export.temporary_handler("demo.Optional", handler, required=False):
            self.assertIn("demo.Optional", subject_export.registered_domains())
            self.assertNotIn("demo.Optional", subject_export.required_domains())

    def test_temporary_handler_restores_previous_on_exit(self):
        def original(employee):
            return subject_export.DomainExportResult(status=subject_export.DomainStatus.NO_RECORDS)

        def replacement(employee):
            return subject_export.DomainExportResult(status=subject_export.DomainStatus.EXCLUDED)

        subject_export.register("demo.Thing", original)
        try:
            with subject_export.temporary_handler("demo.Thing", replacement):
                self.assertIn("demo.Thing", subject_export.registered_domains())
            self.assertIn("demo.Thing", subject_export.registered_domains())
        finally:
            subject_export.unregister("demo.Thing")
        self.assertNotIn("demo.Thing", subject_export.registered_domains())


class RunSubjectExportTests(TestCase):
    def setUp(self):
        self.dept, self.level, self.grade, self.location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="ESE1", first_name="Sub", last_name="Ject", date_of_birth=date(1990, 1, 1),
            work_email="sub.ject@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )

    def test_included_domain_contributes_its_payload(self):
        def handler(employee):
            return subject_export.DomainExportResult(
                status=subject_export.DomainStatus.INCLUDED, record_count=1, payload={"a": 1},
            )

        with subject_export.temporary_handler("demo.Included", handler):
            payload, manifest = subject_export.run_subject_export(self.employee)

        self.assertEqual(payload["demo.Included"], {"a": 1})
        self.assertEqual(manifest.domains["demo.Included"].status, subject_export.DomainStatus.INCLUDED)
        self.assertTrue(manifest.complete)

    def test_no_records_domain_does_not_contribute_payload_but_is_in_the_manifest(self):
        def handler(employee):
            return subject_export.DomainExportResult(status=subject_export.DomainStatus.NO_RECORDS)

        with subject_export.temporary_handler("demo.Empty", handler):
            payload, manifest = subject_export.run_subject_export(self.employee)

        self.assertNotIn("demo.Empty", payload)
        self.assertEqual(manifest.domains["demo.Empty"].status, subject_export.DomainStatus.NO_RECORDS)

    def test_a_failing_required_domain_is_isolated_and_makes_the_manifest_incomplete(self):
        def boom(employee):
            raise RuntimeError("simulated failure")

        with subject_export.temporary_handler("demo.Boom", boom):
            payload, manifest = subject_export.run_subject_export(self.employee)

        self.assertNotIn("demo.Boom", payload)
        self.assertEqual(manifest.domains["demo.Boom"].status, subject_export.DomainStatus.FAILED)
        self.assertFalse(manifest.complete)

    def test_a_failing_non_required_domain_does_not_make_the_manifest_incomplete(self):
        def boom(employee):
            raise RuntimeError("simulated failure")

        with subject_export.temporary_handler("demo.Boom", boom, required=False):
            payload, manifest = subject_export.run_subject_export(self.employee)

        self.assertEqual(manifest.domains["demo.Boom"].status, subject_export.DomainStatus.FAILED)
        self.assertTrue(manifest.complete)

    def test_one_domain_failing_does_not_block_siblings(self):
        def boom(employee):
            raise RuntimeError("simulated failure")

        def fine(employee):
            return subject_export.DomainExportResult(status=subject_export.DomainStatus.INCLUDED, payload="ok")

        with (
            subject_export.temporary_handler("demo.Boom", boom),
            subject_export.temporary_handler("demo.Fine", fine),
        ):
            payload, manifest = subject_export.run_subject_export(self.employee)

        self.assertEqual(payload["demo.Fine"], "ok")
        self.assertEqual(manifest.domains["demo.Fine"].status, subject_export.DomainStatus.INCLUDED)


class BuiltinRegistrationsTests(TestCase):
    """Confirms each app's AppConfig.ready() actually registered its
    handler under the name the registry dispatches by -- not just that
    the handler function exists (mirrors core_hr's
    IdentityVerificationHandlersAreWiredUpTests)."""

    def test_documents_core_bundle_is_registered(self):
        self.assertIn("documents.core_bundle", subject_export.registered_domains())
        self.assertIn("documents.core_bundle", subject_export.required_domains())

    def test_compensation_proposals_are_registered(self):
        self.assertIn("compensation.CompProposal", subject_export.registered_domains())

    def test_learning_training_records_are_registered(self):
        self.assertIn("learning.TrainingRecord", subject_export.registered_domains())
