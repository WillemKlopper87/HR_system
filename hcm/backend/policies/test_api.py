from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Policy, PolicyAcknowledgment, PolicyChunk
from .services import create_policy, publish_policy

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class PolicyApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1985, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2015, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="hradmin", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.plain_employee = Employee.objects.hire(
            employee_number="E100", first_name="Plain", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="plain@example.com", hire_date=date(2021, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="plain", password="x"),
        )
        RoleAssignment.objects.create(employee=self.plain_employee, role=Role.objects.get(name="employee"))

        self.other_employee = Employee.objects.hire(
            employee_number="E101", first_name="Other", last_name="Employee", date_of_birth=date(1991, 1, 1),
            work_email="other@example.com", hire_date=date(2021, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="other", password="x"),
        )
        RoleAssignment.objects.create(employee=self.other_employee, role=Role.objects.get(name="employee"))


class PolicyPermissionApiTests(PolicyApiTestCase):
    def test_plain_employee_can_read_but_not_create_policies(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/policies/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            "/api/v1/policies/", {"title": "New Policy", "category": "other", "body": "..."}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_create_policy(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/policies/", {"title": "Code of Conduct", "category": "code_of_conduct", "body": "Behave."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["code"], "code-of-conduct")
        self.assertEqual(response.data["version"], 1)
        self.assertEqual(response.data["status"], "draft")

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/v1/policies/")
        self.assertIn(response.status_code, (401, 403))


class PolicyWorkflowApiTests(PolicyApiTestCase):
    def test_hr_admin_can_publish_a_draft_policy(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/policies/{policy.id}/publish/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "published")

    def test_plain_employee_cannot_publish(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.post(f"/api/v1/policies/{policy.id}/publish/")
        self.assertEqual(response.status_code, 403)

    def test_publishing_twice_is_rejected(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.hr_admin.user)
        self.client.post(f"/api/v1/policies/{policy.id}/publish/")
        response = self.client.post(f"/api/v1/policies/{policy.id}/publish/")
        self.assertEqual(response.status_code, 400)

    def test_new_version_action_creates_a_draft_under_the_same_code(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        publish_policy(policy, actor=self.hr_admin)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/policies/{policy.id}/new_version/", {"body": "v2"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["code"], policy.code)
        self.assertEqual(response.data["version"], 2)
        self.assertEqual(response.data["status"], "draft")

    def test_published_policy_cannot_be_patched_directly(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        publish_policy(policy, actor=self.hr_admin)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.patch(f"/api/v1/policies/{policy.id}/", {"body": "sneaky edit"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_draft_policy_can_be_patched_directly(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.patch(f"/api/v1/policies/{policy.id}/", {"body": "v1 edited"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["body"], "v1 edited")


class PolicyAcknowledgmentApiTests(PolicyApiTestCase):
    def setUp(self):
        super().setUp()
        self.policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        publish_policy(self.policy, actor=self.hr_admin)

    def test_employee_can_acknowledge_a_published_policy(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.post("/api/v1/policy-acknowledgments/", {"policy": self.policy.id}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["employee"], self.plain_employee.id)

    def test_acknowledgment_ignores_client_supplied_employee(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.post(
            "/api/v1/policy-acknowledgments/", {"policy": self.policy.id, "employee": self.other_employee.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["employee"], self.plain_employee.id)

    def test_hr_admin_cannot_acknowledge_on_behalf_of_someone_else(self):
        """Unlike BenefitsElection, hr_admin has no on-behalf-of path here —
        acknowledgment is always self, even for hr_admin."""
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/policy-acknowledgments/", {"policy": self.policy.id, "employee": self.plain_employee.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["employee"], self.hr_admin.id)

    def test_employee_sees_only_own_acknowledgments_in_list(self):
        PolicyAcknowledgment.objects.create(employee=self.other_employee, policy=self.policy)
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/policy-acknowledgments/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_hr_admin_sees_all_acknowledgments(self):
        PolicyAcknowledgment.objects.create(employee=self.plain_employee, policy=self.policy)
        PolicyAcknowledgment.objects.create(employee=self.other_employee, policy=self.policy)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/policy-acknowledgments/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)

    def test_employee_cannot_read_someone_elses_acknowledgment_by_id(self):
        ack = PolicyAcknowledgment.objects.create(employee=self.other_employee, policy=self.policy)
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/policy-acknowledgments/{ack.id}/")
        self.assertEqual(response.status_code, 403)

    def test_cannot_acknowledge_a_draft_policy_via_api(self):
        draft = create_policy(title="Draft Only Policy", category=Policy.Category.OTHER, body="...")
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.post("/api/v1/policy-acknowledgments/", {"policy": draft.id}, format="json")
        self.assertEqual(response.status_code, 400)


class PolicyAcknowledgmentDashboardApiTests(PolicyApiTestCase):
    def test_non_hr_admin_cannot_view_dashboard(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/dashboards/policy-acknowledgment/")
        self.assertEqual(response.status_code, 403)

    def test_dashboard_reports_acknowledgment_percentage(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        publish_policy(policy, actor=self.hr_admin)
        PolicyAcknowledgment.objects.create(employee=self.plain_employee, policy=policy)

        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/policy-acknowledgment/")
        self.assertEqual(response.status_code, 200)
        row = next(r for r in response.data["policies"] if r["policy_id"] == policy.id)
        self.assertEqual(row["acknowledged_count"], 1)
        # 3 employees seeded in setUp (hr_admin, plain_employee, other_employee).
        self.assertEqual(row["total_employees"], 3)
        self.assertAlmostEqual(row["acknowledged_pct"], round(1 / 3 * 100, 1))


class PolicyDocumentUploadApiTests(PolicyApiTestCase):
    def test_hr_admin_can_create_a_policy_by_uploading_a_txt_file(self):
        upload = SimpleUploadedFile("handbook.txt", b"All leave requests need manager approval.", content_type="text/plain")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/policies/",
            {"title": "Leave Policy", "category": "leave", "source_file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["body"], "All leave requests need manager approval.")
        self.assertTrue(response.data["has_source_file"])
        self.assertIsNotNone(response.data["download_url"])
        self.assertNotIn("source_file", response.data)  # write-only — never echoed back
        self.assertEqual(response.data["chunk_count"], 1)

    def test_uploading_an_unsupported_file_type_is_rejected(self):
        upload = SimpleUploadedFile("policy.exe", b"binary junk", content_type="application/octet-stream")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/policies/",
            {"title": "Bad Policy", "category": "other", "source_file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_chunks_action_returns_generated_passages(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="Paragraph one.\n\nParagraph two.")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/policies/{policy.id}/chunks/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), PolicyChunk.objects.filter(policy=policy).count())

    def test_plain_employee_cannot_view_chunks_of_a_draft_policy(self):
        """IsHRAdminOrReadOnly is read-open on SAFE_METHODS, but
        get_queryset() restricts non-hr_admin requesters to PUBLISHED
        policies regardless — a draft isn't readable at all yet, chunks
        included (both routes share the same queryset)."""
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/policies/{policy.id}/chunks/")
        self.assertEqual(response.status_code, 404)

    def test_plain_employee_can_view_chunks_of_a_published_policy(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        publish_policy(policy, actor=self.hr_admin)
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/policies/{policy.id}/chunks/")
        self.assertEqual(response.status_code, 200)

    def test_plain_employee_does_not_see_draft_policies_in_list(self):
        create_policy(title="Draft Only", category=Policy.Category.OTHER, body="...")
        published = create_policy(title="Published One", category=Policy.Category.OTHER, body="...")
        publish_policy(published, actor=self.hr_admin)
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/policies/")
        self.assertEqual(response.status_code, 200)
        titles = {row["title"] for row in response.data["results"]}
        self.assertEqual(titles, {"Published One"})

    def test_plain_employee_cannot_retrieve_a_draft_policy_directly(self):
        policy = create_policy(title="Draft Only", category=Policy.Category.OTHER, body="...")
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/policies/{policy.id}/")
        self.assertEqual(response.status_code, 404)

    def test_hr_admin_still_sees_draft_policies(self):
        create_policy(title="Draft Only", category=Policy.Category.OTHER, body="...")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/policies/?status=draft")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_download_action_requires_publication_for_non_hr_admin(self):
        upload = SimpleUploadedFile("handbook.txt", b"Confidential draft content.", content_type="text/plain")
        self.client.force_authenticate(user=self.hr_admin.user)
        create = self.client.post(
            "/api/v1/policies/", {"title": "Draft Doc", "category": "other", "source_file": upload}, format="multipart",
        )
        policy_id = create.data["id"]

        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/policies/{policy_id}/download/")
        self.assertEqual(response.status_code, 404)

    def test_download_action_streams_the_real_file_once_published(self):
        upload = SimpleUploadedFile("handbook.txt", b"Everyone must arrive on time.", content_type="text/plain")
        self.client.force_authenticate(user=self.hr_admin.user)
        create = self.client.post(
            "/api/v1/policies/", {"title": "Attendance Policy", "category": "other", "source_file": upload}, format="multipart",
        )
        policy = Policy.objects.get(pk=create.data["id"])
        publish_policy(policy, actor=self.hr_admin)

        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/policies/{policy.id}/download/")
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content)
        self.assertEqual(content, b"Everyone must arrive on time.")

    def test_patching_draft_body_regenerates_chunks(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="Short.")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.patch(
            f"/api/v1/policies/{policy.id}/",
            {"body": "A brand new body.\n\nWith two paragraphs now."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["chunk_count"], 1)
        chunk = PolicyChunk.objects.get(policy=policy)
        self.assertIn("two paragraphs", chunk.text)
