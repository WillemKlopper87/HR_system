"""C6 careers portal (design spec §3.4, §6) -- the public, unauthenticated,
write-capable surface. Tests deliberately mirror
rbac_audit/test_throttling.py's LoginThrottleTests shape for the new
throttle scopes, since the design spec explicitly models this endpoint's
anti-abuse posture on login's."""
from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rbac_audit.models import ConsentRecord
from rest_framework.test import APIClient

from .models import Applicant, Requisition
from .validation import MAX_RESUME_SIZE_BYTES

User = get_user_model()


def _pdf(name="cv.pdf", content=b"%PDF-1.7\nresume content"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


class CareersApiTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.dept = Department.objects.create(name="Engineering", code="ENG")
        self.level = OccupationalLevel.objects.get(code="TOP")
        self.grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=self.level)
        self.location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)

        self.recruiter = Employee.objects.hire(
            employee_number="R001", first_name="Rita", last_name="Recruiter", date_of_birth=date(1985, 1, 1),
            work_email="rita@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="rita-careers", password="x"),
        )

        self.open_external = Requisition.objects.create(
            title="Backend Engineer", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN, opened_at=date(2026, 7, 1),
            external_posting=True, description="Build things.",
        )
        self.open_internal_only = Requisition.objects.create(
            title="Internal Only Role", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN, opened_at=date(2026, 7, 1),
            external_posting=False,
        )
        self.closed_external = Requisition.objects.create(
            title="Closed Role", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.CLOSED, opened_at=date(2026, 6, 1),
            external_posting=True,
        )

    def _apply(self, **overrides):
        payload = {
            "requisition": self.open_external.id, "first_name": "Portal", "last_name": "Applicant",
            "email": "portal.applicant@example.com", "phone": "0821234567", "date_of_birth": "1995-05-05",
            "resume": _pdf(),
        }
        payload.update(overrides)
        return self.client.post("/api/v1/careers/apply/", payload, format="multipart")


class PublicPostingsListTests(CareersApiTestCase):
    def test_only_open_and_externally_posted_requisitions_are_listed(self):
        response = self.client.get("/api/v1/careers/postings/")
        self.assertEqual(response.status_code, 200)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.open_external.id})

    def test_posting_detail_is_narrow(self):
        response = self.client.get(f"/api/v1/careers/postings/{self.open_external.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Backend Engineer")
        self.assertEqual(response.data["description"], "Build things.")
        self.assertNotIn("hiring_manager", response.data)
        self.assertNotIn("headcount", response.data)
        self.assertNotIn("positions", response.data)

    def test_closed_or_internal_only_requisition_is_not_reachable_by_id(self):
        self.assertEqual(self.client.get(f"/api/v1/careers/postings/{self.closed_external.id}/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/v1/careers/postings/{self.open_internal_only.id}/").status_code, 404
        )

    def test_no_login_required(self):
        # APIClient here never calls force_authenticate anywhere in this
        # file -- every request in this whole module is genuinely anonymous.
        response = self.client.get("/api/v1/careers/postings/")
        self.assertEqual(response.status_code, 200)


class PublicApplicationTests(CareersApiTestCase):
    def test_valid_submission_creates_a_real_applicant_with_portal_source(self):
        response = self._apply()
        self.assertEqual(response.status_code, 201, response.data)
        applicant = Applicant.objects.get(email="portal.applicant@example.com")
        self.assertEqual(applicant.source, Applicant.Source.PORTAL)
        self.assertEqual(applicant.requisition_id, self.open_external.id)
        self.assertEqual(applicant.current_stage, Applicant.Stage.APPLIED)
        self.assertEqual(applicant.resume_content_type, "application/pdf")
        # Same pipeline as an internally-created applicant -- no separate
        # shape downstream needs to know about (design spec §2.5).
        self.assertTrue(applicant.can_transition_to(Applicant.Stage.SCREENED))

    def test_application_to_a_non_externally_posted_requisition_is_rejected_not_500(self):
        response = self._apply(requisition=self.open_internal_only.id)
        self.assertEqual(response.status_code, 400)

    def test_application_to_a_closed_requisition_is_rejected_not_500(self):
        response = self._apply(requisition=self.closed_external.id)
        self.assertEqual(response.status_code, 400)

    def test_duplicate_email_for_same_requisition_is_a_clean_400(self):
        first = self._apply()
        self.assertEqual(first.status_code, 201, first.data)
        second = self._apply()
        self.assertEqual(second.status_code, 400)
        self.assertNotEqual(second.status_code, 500)

    def test_same_email_different_requisition_is_allowed(self):
        other = Requisition.objects.create(
            title="Frontend Engineer", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN, external_posting=True,
        )
        first = self._apply()
        self.assertEqual(first.status_code, 201, first.data)
        second = self._apply(requisition=other.id)
        self.assertEqual(second.status_code, 201, second.data)

    def test_unrecognised_resume_content_is_rejected(self):
        bad_file = SimpleUploadedFile("cv.pdf", b"not actually a pdf", content_type="application/pdf")
        response = self._apply(resume=bad_file)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Applicant.objects.filter(email="portal.applicant@example.com").exists())

    def test_oversized_resume_is_rejected(self):
        oversized = SimpleUploadedFile(
            "cv.pdf", b"%PDF-1.7\n" + b"0" * (MAX_RESUME_SIZE_BYTES + 1), content_type="application/pdf"
        )
        response = self._apply(resume=oversized)
        self.assertEqual(response.status_code, 400)

    def test_honeypot_field_silently_no_ops(self):
        response = self._apply(website="http://spam.example.com")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(Applicant.objects.filter(email="portal.applicant@example.com").exists())

    def test_demographic_fields_dropped_without_consent(self):
        response = self._apply(race="african", gender="female", disability_status="no")
        self.assertEqual(response.status_code, 201, response.data)
        applicant = Applicant.objects.get(email="portal.applicant@example.com")
        self.assertEqual(applicant.race, "not_disclosed")
        self.assertEqual(applicant.gender, "not_disclosed")
        self.assertEqual(applicant.disability_status, "not_disclosed")
        self.assertFalse(
            ConsentRecord.objects.filter(applicant=applicant, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID).exists()
        )

    def test_demographic_fields_persisted_with_consent_and_a_consent_record_is_created(self):
        response = self._apply(
            race="african", gender="female", disability_status="no", demographic_consent=True,
        )
        self.assertEqual(response.status_code, 201, response.data)
        applicant = Applicant.objects.get(email="portal.applicant@example.com")
        self.assertEqual(applicant.race, "african")
        self.assertEqual(applicant.gender, "female")
        self.assertEqual(applicant.disability_status, "no")
        self.assertTrue(
            ConsentRecord.objects.filter(applicant=applicant, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID).exists()
        )

    def test_invalid_date_of_birth_is_a_clean_400(self):
        response = self._apply(date_of_birth="not-a-date")
        self.assertEqual(response.status_code, 400)

    def test_missing_resume_is_a_clean_400(self):
        response = self.client.post(
            "/api/v1/careers/apply/",
            {
                "requisition": self.open_external.id, "first_name": "No", "last_name": "Resume",
                "email": "noresume@example.com", "date_of_birth": "1995-05-05",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)


class CareersThrottleTests(CareersApiTestCase):
    def test_burst_throttle_kicks_in(self):
        # 5/min per IP (config/settings.py THROTTLE_CAREERS_APPLICATION_BURST)
        for i in range(5):
            response = self.client.post(
                "/api/v1/careers/apply/", {"email": f"burst{i}@example.com"}, format="multipart",
                REMOTE_ADDR="10.1.1.1",
            )
            self.assertEqual(response.status_code, 400)  # incomplete payload, but still counts toward the throttle
        blocked = self.client.post(
            "/api/v1/careers/apply/", {"email": "burst-blocked@example.com"}, format="multipart",
            REMOTE_ADDR="10.1.1.1",
        )
        self.assertEqual(blocked.status_code, 429)

    def test_per_email_throttle_is_independent_of_ip(self):
        # 3/hour per email (THROTTLE_CAREERS_APPLICATION_EMAIL) -- a
        # distributed-IP attacker hammering one email doesn't evade this.
        for i in range(3):
            response = self.client.post(
                "/api/v1/careers/apply/", {"email": "target@example.com"}, format="multipart",
                REMOTE_ADDR=f"10.2.2.{i + 1}",
            )
            self.assertEqual(response.status_code, 400)
        blocked = self.client.post(
            "/api/v1/careers/apply/", {"email": "target@example.com"}, format="multipart",
            REMOTE_ADDR="10.2.2.99",
        )
        self.assertEqual(blocked.status_code, 429)
        # a different email from the same never-before-seen IP is unaffected
        other = self.client.post(
            "/api/v1/careers/apply/", {"email": "someone-else@example.com"}, format="multipart",
            REMOTE_ADDR="10.2.2.100",
        )
        self.assertEqual(other.status_code, 400)
