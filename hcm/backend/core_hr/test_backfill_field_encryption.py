"""HCM remediation H-4, phase 1: core_hr.management.commands.backfill_field_encryption."""
from __future__ import annotations

from datetime import date
from io import StringIO

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase
from rbac_audit.models import TOTPDevice

from .models import Department, Employee, JobGrade, Location, OccupationalLevel


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG-BF")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="GBF1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HOBF", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class BackfillFieldEncryptionTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.dept, self.level, self.grade, self.location = dept, level, grade, location
        self.employee = Employee.objects.hire(
            employee_number="EBF1", first_name="Back", last_name="Fill", date_of_birth=date(1990, 1, 1),
            work_email="back.fill@example.com", hire_date=date(2024, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
            national_id_number="8001015009087", passport_number="P1234567",
        )
        self.device = TOTPDevice.objects.create(employee=self.employee, secret="JBSWY3DPEHPK3PXP")

    def _call(self, *args):
        out = StringIO()
        call_command("backfill_field_encryption", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_reports_counts_and_writes_nothing(self):
        output = self._call("--dry-run")
        self.assertIn("1 row(s) would be backfilled", output)
        self.employee.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.employee.national_id_number_encrypted, "")
        self.assertEqual(self.device.secret_encrypted, "")

    def test_backfill_populates_encrypted_mirrors_without_touching_plaintext(self):
        self._call()
        self.employee.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.employee.national_id_number_encrypted, "8001015009087")
        self.assertEqual(self.employee.passport_number_encrypted, "P1234567")
        self.assertEqual(self.device.secret_encrypted, "JBSWY3DPEHPK3PXP")
        # Plaintext originals are untouched -- phase 1 is additive only.
        self.assertEqual(self.employee.national_id_number, "8001015009087")
        self.assertEqual(self.device.secret, "JBSWY3DPEHPK3PXP")

    def test_backfill_is_idempotent_and_skips_already_backfilled_rows(self):
        self._call()
        self.employee.refresh_from_db()
        first_ciphertext_value = self.employee.national_id_number_encrypted
        output = self._call()
        self.assertIn("nothing to backfill", output)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.national_id_number_encrypted, first_ciphertext_value)

    def test_employee_with_blank_restricted_fields_is_skipped(self):
        blank_employee = Employee.objects.hire(
            employee_number="EBF2", first_name="No", last_name="Ids", date_of_birth=date(1990, 1, 1),
            work_email="no.ids@example.com", hire_date=date(2024, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        self._call()
        blank_employee.refresh_from_db()
        self.assertEqual(blank_employee.national_id_number_encrypted, "")

    def test_verify_passes_after_a_correct_backfill(self):
        self._call()
        output = self._call("--verify")
        self.assertIn("Verified", output)
        self.assertIn("3 backfilled row(s)", output)  # national_id + passport + totp secret

    def test_verify_fails_when_a_backfilled_value_does_not_match_the_plaintext(self):
        self._call()
        # Simulate drift: the plaintext changed after backfill without a re-run.
        Employee.objects.filter(pk=self.employee.pk).update(national_id_number="8001015009999")
        with self.assertRaises(CommandError):
            self._call("--verify")

    def test_verify_reports_a_value_that_cannot_be_decrypted_at_all(self):
        self._call()
        # Simulate corruption directly at the DB layer, bypassing the
        # field's own get_prep_value() (which would just re-encrypt a
        # plain .update() value rather than store it raw) -- something
        # that isn't valid ciphertext under any configured key.
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE core_hr_employee SET national_id_number_encrypted = %s WHERE id = %s",
                ["not-valid-ciphertext", self.employee.pk],
            )
        with self.assertRaises(CommandError):
            self._call("--verify")
