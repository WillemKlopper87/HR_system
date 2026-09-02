from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Policy, PolicyAcknowledgment, PolicyChunk
from .services import create_policy, publish_policy, record_policy_approval

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

        self.committee_member = Employee.objects.hire(
            employee_number="E102", first_name="Committee", last_name="Member", date_of_birth=date(1988, 1, 1),
            work_email="committee@example.com", hire_date=date(2019, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="committee", password="x"),
        )
        RoleAssignment.objects.create(
            employee=self.committee_member, role=Role.objects.get(name="policy_committee_member")
        )

    def _approve(self, policy):
        """publish_policy now requires every current policy_committee_member
        to have approved the exact draft first -- shared setup step for
        every test in this file that isn't itself testing the approval
        gate (see PolicyCommitteeApprovalApiTests below)."""
        record_policy_approval(policy, approver=self.committee_member)


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
        self._approve(policy)
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
        self._approve(policy)
        self.client.force_authenticate(user=self.hr_admin.user)
        first = self.client.post(f"/api/v1/policies/{policy.id}/publish/")
        self.assertEqual(first.status_code, 200, first.data)
        response = self.client.post(f"/api/v1/policies/{policy.id}/publish/")
        self.assertEqual(response.status_code, 400)

    def test_new_version_action_creates_a_draft_under_the_same_code(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._approve(policy)
        publish_policy(policy, actor=self.hr_admin)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/policies/{policy.id}/new_version/", {"body": "v2"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["code"], policy.code)
        self.assertEqual(response.data["version"], 2)
        self.assertEqual(response.data["status"], "draft")

    def test_published_policy_cannot_be_patched_directly(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._approve(policy)
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
        self._approve(self.policy)
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
        self._approve(policy)
        publish_policy(policy, actor=self.hr_admin)
        PolicyAcknowledgment.objects.create(employee=self.plain_employee, policy=policy)

        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/policy-acknowledgment/")
        self.assertEqual(response.status_code, 200)
        row = next(r for r in response.data["policies"] if r["policy_id"] == policy.id)
        self.assertEqual(row["acknowledged_count"], 1)
        # 4 employees seeded in setUp (hr_admin, plain_employee, other_employee, committee_member).
        self.assertEqual(row["total_employees"], 4)
        self.assertAlmostEqual(row["acknowledged_pct"], round(1 / 4 * 100, 1))


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

    def _upload(self, name, content, content_type="application/octet-stream"):
        self.client.force_authenticate(user=self.hr_admin.user)
        return self.client.post(
            "/api/v1/policies/",
            {"title": "Sniffed", "category": "other", "source_file": SimpleUploadedFile(name, content, content_type=content_type)},
            format="multipart",
        )

    def test_a_pdf_that_is_not_a_pdf_is_a_clean_400_not_a_500(self):
        # H2 (brief D4): the extension used to be trusted, so pypdf blew up on
        # this with a 500. Content is sniffed first now.
        response = self._upload("policy.pdf", b"this is really just text pretending", "application/pdf")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("does not look like a PDF", str(response.data))

    def test_a_docx_that_is_not_a_zip_is_a_clean_400(self):
        response = self._upload("policy.docx", b"not a zip archive at all")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("does not look like a Word", str(response.data))

    def test_a_corrupt_pdf_with_the_right_magic_is_a_clean_400(self):
        response = self._upload("policy.pdf", b"%PDF-1.7\n garbage that pypdf cannot parse", "application/pdf")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("could not be read", str(response.data))

    def test_binary_masquerading_as_txt_is_rejected(self):
        response = self._upload("policy.txt", b"MZ\x00\x00\x01\x02 binary payload \x00", "text/plain")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("not a text file", str(response.data))

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
        self._approve(policy)
        publish_policy(policy, actor=self.hr_admin)
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get(f"/api/v1/policies/{policy.id}/chunks/")
        self.assertEqual(response.status_code, 200)

    def test_plain_employee_does_not_see_draft_policies_in_list(self):
        create_policy(title="Draft Only", category=Policy.Category.OTHER, body="...")
        published = create_policy(title="Published One", category=Policy.Category.OTHER, body="...")
        self._approve(published)
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
        self._approve(policy)
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


class PolicyCommitteeApprovalApiTests(PolicyApiTestCase):
    def test_committee_member_can_approve_a_draft(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.committee_member.user)
        response = self.client.post(f"/api/v1/policies/{policy.id}/approve/", {"comment": "Looks good."}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["approved_by"], self.committee_member.id)

    def test_non_committee_member_cannot_approve(self):
        # hr_admin authors and publishes policies but isn't automatically a
        # committee member -- the two are separate roles by design.
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/policies/{policy.id}/approve/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_committee_member_can_read_a_draft_policy(self):
        # get_queryset() widens draft visibility to committee members
        # specifically so they can review what they're being asked to
        # approve -- a plain employee still gets a 404 on the same URL.
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.committee_member.user)
        response = self.client.get(f"/api/v1/policies/{policy.id}/")
        self.assertEqual(response.status_code, 200, response.data)

    def test_approving_via_the_api_is_idempotent(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.committee_member.user)
        first = self.client.post(f"/api/v1/policies/{policy.id}/approve/", {}, format="json")
        second = self.client.post(f"/api/v1/policies/{policy.id}/approve/", {}, format="json")
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(policy.approvals.count(), 1)

    def test_publish_reports_who_is_still_pending_then_succeeds_once_approved(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self.client.force_authenticate(user=self.hr_admin.user)
        blocked = self.client.post(f"/api/v1/policies/{policy.id}/publish/")
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("Committee Member", blocked.data["detail"])

        detail = self.client.get(f"/api/v1/policies/{policy.id}/").data
        self.assertEqual(detail["pending_committee_approvals"], ["Committee Member"])

        self.client.force_authenticate(user=self.committee_member.user)
        self.client.post(f"/api/v1/policies/{policy.id}/approve/", {}, format="json")

        self.client.force_authenticate(user=self.hr_admin.user)
        published = self.client.post(f"/api/v1/policies/{policy.id}/publish/")
        self.assertEqual(published.status_code, 200, published.data)
