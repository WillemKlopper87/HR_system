"""HCM remediation H-4: rbac_audit.field_encryption + rbac_audit.fields."""
from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.db import connection
from django.test import TestCase

from . import field_encryption as fe
from .models import TOTPDevice


class EncryptDecryptTests(TestCase):
    def test_round_trip(self):
        ciphertext = fe.encrypt_value("8001015009087", purpose="national_id")
        self.assertEqual(fe.decrypt_value(ciphertext, purpose="national_id"), "8001015009087")

    def test_ciphertext_does_not_contain_the_plaintext(self):
        plaintext = "8001015009087"
        ciphertext = fe.encrypt_value(plaintext, purpose="national_id")
        self.assertNotIn(plaintext, ciphertext)

    def test_two_encryptions_of_the_same_value_differ(self):
        """Fernet includes a fresh IV/timestamp per call -- ciphertext is
        not a deterministic function of plaintext (unlike a bare hash),
        so equal plaintexts don't reveal themselves as equal ciphertexts."""
        a = fe.encrypt_value("8001015009087", purpose="national_id")
        b = fe.encrypt_value("8001015009087", purpose="national_id")
        self.assertNotEqual(a, b)

    def test_cross_purpose_decryption_is_rejected(self):
        ciphertext = fe.encrypt_value("JBSWY3DPEHPK3PXP", purpose="totp_seed")
        with self.assertRaises(fe.FieldDecryptionError):
            fe.decrypt_value(ciphertext, purpose="national_id")

    def test_corrupted_ciphertext_is_rejected_not_silently_wrong(self):
        ciphertext = fe.encrypt_value("8001015009087", purpose="national_id")
        tampered = ciphertext[:-4] + ("A" if ciphertext[-4] != "A" else "B") + ciphertext[-3:]
        with self.assertRaises(fe.FieldDecryptionError):
            fe.decrypt_value(tampered, purpose="national_id")

    def test_lookup_fingerprint_is_deterministic_and_keyed(self):
        fp1 = fe.lookup_fingerprint("8001015009087", purpose="national_id")
        fp2 = fe.lookup_fingerprint("8001015009087", purpose="national_id")
        self.assertEqual(fp1, fp2)
        # Different purpose -> different fingerprint for the same value,
        # same purpose-isolation guarantee as encryption itself.
        fp3 = fe.lookup_fingerprint("8001015009087", purpose="passport_number")
        self.assertNotEqual(fp1, fp3)


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG-FE")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="GFE1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HOFE", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class EncryptedCharFieldModelTests(TestCase):
    """Exercises EncryptedCharField through real models (core_hr.Employee's
    national_id_number_encrypted, rbac_audit.TOTPDevice.secret_encrypted)
    rather than a standalone test model, so this proves the actual
    production wiring, not just the field class in isolation."""

    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="EFE1", first_name="Field", last_name="Enc", date_of_birth=date(1990, 1, 1),
            work_email="field.enc@example.com", hire_date=date(2024, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )

    def test_assigning_and_reading_back_round_trips_transparently(self):
        self.employee.national_id_number_encrypted = "8001015009087"
        self.employee.save(update_fields=["national_id_number_encrypted"])
        fetched = Employee.objects.get(pk=self.employee.pk)
        self.assertEqual(fetched.national_id_number_encrypted, "8001015009087")

    def test_raw_database_column_holds_ciphertext_not_plaintext(self):
        self.employee.national_id_number_encrypted = "8001015009087"
        self.employee.save(update_fields=["national_id_number_encrypted"])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT national_id_number_encrypted FROM core_hr_employee WHERE id = %s", [self.employee.pk]
            )
            raw_value = cursor.fetchone()[0]
        self.assertNotEqual(raw_value, "8001015009087")
        self.assertNotIn("8001015009087", raw_value)

    def test_blank_value_stays_blank_both_ways(self):
        self.employee.national_id_number_encrypted = ""
        self.employee.save(update_fields=["national_id_number_encrypted"])
        fetched = Employee.objects.get(pk=self.employee.pk)
        self.assertEqual(fetched.national_id_number_encrypted, "")

    def test_totp_secret_encrypted_round_trips_and_is_not_plaintext_in_the_database(self):
        device = TOTPDevice.objects.create(employee=self.employee, secret_encrypted="JBSWY3DPEHPK3PXP")
        fetched = TOTPDevice.objects.get(pk=device.pk)
        self.assertEqual(fetched.secret_encrypted, "JBSWY3DPEHPK3PXP")
        with connection.cursor() as cursor:
            cursor.execute("SELECT secret_encrypted FROM rbac_audit_totpdevice WHERE id = %s", [device.pk])
            raw_value = cursor.fetchone()[0]
        self.assertNotIn("JBSWY3DPEHPK3PXP", raw_value)
