from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.consent import record_consent
from rbac_audit.models import ConsentRecord, Role, RoleAssignment
from rest_framework.test import APIClient

from .services import enroll_employee, run_liveness_check

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(
        name="Head Office", code="HO", province=Location.Province.GAUTENG, latitude=-26.2041, longitude=28.0473
    )
    return dept, level, grade, location


class IdentityVerificationApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        def _hire(number, username, role_name=None):
            emp = Employee.objects.hire(
                employee_number=number, first_name=username.title(), last_name="Test", date_of_birth=date(1985, 1, 1),
                work_email=f"{username}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
                occupational_level=self.level, job_grade=self.grade, location=self.location,
                user=User.objects.create_user(username=username, password="x"),
            )
            if role_name:
                RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name=role_name))
            return emp

        self.hr_admin = _hire("HR1", "hradmin", "hr_admin")
        self.auditor = _hire("AUD1", "auditor", "auditor")
        self.alice = _hire("E100", "alice")
        self.bob = _hire("E101", "bob")

        self.descriptor = [0.1] * 128

    def _grant_consent(self, employee):
        record_consent(
            employee=employee, purpose=ConsentRecord.Purpose.BIOMETRIC,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )


class EnrollmentApiTests(IdentityVerificationApiTestCase):
    def test_enroll_without_consent_is_rejected(self):
        self.client.force_authenticate(user=self.alice.user)
        response = self.client.post(
            "/api/v1/biometric-enrollments/", {"employee": self.alice.id, "descriptor": self.descriptor}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_employee_can_enroll_self(self):
        self._grant_consent(self.alice)
        self.client.force_authenticate(user=self.alice.user)
        response = self.client.post(
            "/api/v1/biometric-enrollments/", {"employee": self.alice.id, "descriptor": self.descriptor}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("descriptor", response.data)

    def test_employee_cannot_enroll_someone_else(self):
        self._grant_consent(self.bob)
        self.client.force_authenticate(user=self.alice.user)
        response = self.client.post(
            "/api/v1/biometric-enrollments/", {"employee": self.bob.id, "descriptor": self.descriptor}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_enroll_on_behalf_of_an_employee(self):
        self._grant_consent(self.alice)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/biometric-enrollments/", {"employee": self.alice.id, "descriptor": self.descriptor}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_wrong_length_descriptor_is_rejected(self):
        self._grant_consent(self.alice)
        self.client.force_authenticate(user=self.alice.user)
        response = self.client.post(
            "/api/v1/biometric-enrollments/", {"employee": self.alice.id, "descriptor": [0.1] * 50}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_employee_cannot_see_a_colleagues_enrollment(self):
        self._grant_consent(self.bob)
        enroll_employee(employee=self.bob, descriptor=self.descriptor)
        self.client.force_authenticate(user=self.alice.user)
        response = self.client.get(f"/api/v1/biometric-enrollments/?employee={self.bob.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])


class LivenessCheckApiTests(IdentityVerificationApiTestCase):
    def setUp(self):
        super().setUp()
        self._grant_consent(self.alice)
        enroll_employee(employee=self.alice, descriptor=self.descriptor)

    def test_check_without_enrollment_is_rejected(self):
        self._grant_consent(self.bob)
        self.client.force_authenticate(user=self.bob.user)
        response = self.client.post(
            "/api/v1/liveness-checks/", {"employee": self.bob.id, "descriptor": self.descriptor}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_matching_check_needs_no_review(self):
        self.client.force_authenticate(user=self.alice.user)
        close = self.descriptor[:127] + [self.descriptor[-1] + 0.3]
        response = self.client.post(
            "/api/v1/liveness-checks/", {"employee": self.alice.id, "descriptor": close}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["outcome"], "match")
        self.assertEqual(response.data["review_status"], "not_required")

    def test_colleague_cannot_run_a_check_for_someone_else(self):
        self.client.force_authenticate(user=self.bob.user)
        response = self.client.post(
            "/api/v1/liveness-checks/", {"employee": self.alice.id, "descriptor": self.descriptor}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_colleague_cannot_view_anothers_check(self):
        check = run_liveness_check(employee=self.alice, descriptor=self.descriptor)
        self.client.force_authenticate(user=self.bob.user)
        response = self.client.get(f"/api/v1/liveness-checks/{check.id}/")
        self.assertEqual(response.status_code, 404)

    def test_auditor_can_view_any_check_but_not_review(self):
        far = [0.9] * 128
        check = run_liveness_check(employee=self.alice, descriptor=far)
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get(f"/api/v1/liveness-checks/{check.id}/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/v1/liveness-checks/{check.id}/review/", {"decision": "confirmed_mismatch"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_subject_cannot_review_their_own_flagged_check(self):
        far = [0.9] * 128
        check = run_liveness_check(employee=self.alice, descriptor=far)
        self.client.force_authenticate(user=self.alice.user)
        response = self.client.post(f"/api/v1/liveness-checks/{check.id}/review/", {"decision": "confirmed_match"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_review_a_flagged_check(self):
        far = [0.9] * 128
        check = run_liveness_check(employee=self.alice, descriptor=far)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            f"/api/v1/liveness-checks/{check.id}/review/", {"decision": "confirmed_mismatch", "notes": "Escalated"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["review_status"], "confirmed_mismatch")

    def test_no_descriptor_captured_is_flagged_no_face_detected(self):
        self.client.force_authenticate(user=self.alice.user)
        response = self.client.post("/api/v1/liveness-checks/", {"employee": self.alice.id}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["outcome"], "no_face_detected")
        self.assertEqual(response.data["review_status"], "pending")

    def test_at_office_computed_from_geolocation(self):
        self.client.force_authenticate(user=self.alice.user)
        response = self.client.post(
            "/api/v1/liveness-checks/",
            {"employee": self.alice.id, "descriptor": self.descriptor, "latitude": -26.2041, "longitude": 28.0473},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["at_office"])


class AttendanceSummaryApiTests(IdentityVerificationApiTestCase):
    def setUp(self):
        super().setUp()
        self._grant_consent(self.alice)
        enroll_employee(employee=self.alice, descriptor=self.descriptor)
        run_liveness_check(employee=self.alice, descriptor=self.descriptor, latitude=-26.2041, longitude=28.0473)

    def test_plain_employee_sees_only_their_own_row(self):
        self.client.force_authenticate(user=self.bob.user)
        response = self.client.get("/api/v1/dashboards/attendance/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["employee"], self.bob.id)

    def test_hr_admin_sees_every_employee_including_zero_checks(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/attendance/")
        self.assertEqual(response.status_code, 200)
        employee_ids = {row["employee"] for row in response.data}
        self.assertIn(self.alice.id, employee_ids)
        self.assertIn(self.bob.id, employee_ids)
        alice_row = next(row for row in response.data if row["employee"] == self.alice.id)
        self.assertEqual(alice_row["days_in_office"], 1)
        bob_row = next(row for row in response.data if row["employee"] == self.bob.id)
        self.assertEqual(bob_row["days_in_office"], 0)
