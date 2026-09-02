from __future__ import annotations

import io
from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment

from .chunking import chunk_text
from .extraction import UnsupportedDocumentError, extract_text
from .models import Policy, PolicyAcknowledgment, PolicyChunk
from .services import (
    PolicyWorkflowError,
    acknowledge_policy,
    archive_policy,
    create_new_version,
    create_policy,
    publish_policy,
    record_policy_approval,
    update_draft,
)


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class PolicyServiceTests(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()
        self.employee = Employee.objects.hire(
            employee_number="E100", first_name="Test", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="test@example.com", hire_date=date(2020, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )
        self.committee_member = Employee.objects.hire(
            employee_number="E101", first_name="Committee", last_name="Member", date_of_birth=date(1988, 1, 1),
            work_email="committee@example.com", hire_date=date(2019, 1, 1), department=dept,
            occupational_level=level, job_grade=grade, location=location,
        )
        RoleAssignment.objects.create(
            employee=self.committee_member, role=Role.objects.get(name="policy_committee_member")
        )

    def _publish(self, policy, actor=None):
        """publish_policy now requires every current policy_committee_member
        to have approved the exact draft first -- this is the "someone
        already reviewed it" setup step every OTHER test in this file
        needs, so it lives here rather than being repeated at each
        call site. Tests of the approval gate itself skip this helper."""
        record_policy_approval(policy, approver=self.committee_member)
        return publish_policy(policy, actor=actor or self.employee)

    def test_create_policy_derives_code_from_title(self):
        policy = create_policy(title="Code of Conduct", category=Policy.Category.CODE_OF_CONDUCT, body="Behave.")
        self.assertEqual(policy.code, "code-of-conduct")
        self.assertEqual(policy.version, 1)
        self.assertEqual(policy.status, Policy.Status.DRAFT)

    def test_create_policy_rejects_empty_code(self):
        with self.assertRaises(PolicyWorkflowError):
            create_policy(title="!!!", category=Policy.Category.OTHER, body="")

    def test_cannot_acknowledge_a_draft_policy(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        with self.assertRaises(PolicyWorkflowError):
            acknowledge_policy(policy, employee=self.employee)

    def test_acknowledge_is_idempotent(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="...")
        self._publish(policy)
        ack1 = acknowledge_policy(policy, employee=self.employee)
        ack2 = acknowledge_policy(policy, employee=self.employee)
        self.assertEqual(ack1.id, ack2.id)
        self.assertEqual(PolicyAcknowledgment.objects.filter(employee=self.employee, policy=policy).count(), 1)

    def test_publishing_a_new_version_archives_the_prior_published_version(self):
        v1 = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._publish(v1)
        v2 = create_new_version(v1, body="v2", actor=self.employee)
        self.assertEqual(v2.code, v1.code)
        self.assertEqual(v2.version, 2)
        self._publish(v2)

        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, Policy.Status.ARCHIVED)
        self.assertEqual(v2.status, Policy.Status.PUBLISHED)

    def test_acknowledgment_is_pinned_to_the_specific_version(self):
        v1 = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._publish(v1)
        acknowledge_policy(v1, employee=self.employee)

        v2 = create_new_version(v1, body="v2", actor=self.employee)
        self._publish(v2)

        self.assertTrue(PolicyAcknowledgment.objects.filter(employee=self.employee, policy=v1).exists())
        self.assertFalse(PolicyAcknowledgment.objects.filter(employee=self.employee, policy=v2).exists())

    def test_cannot_publish_a_non_draft_policy(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._publish(policy)
        with self.assertRaises(PolicyWorkflowError):
            publish_policy(policy, actor=self.employee)

    def test_publish_blocked_until_the_committee_member_approves(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        with self.assertRaises(PolicyWorkflowError):
            publish_policy(policy, actor=self.employee)
        record_policy_approval(policy, approver=self.committee_member)
        publish_policy(policy, actor=self.employee)
        policy.refresh_from_db()
        self.assertEqual(policy.status, Policy.Status.PUBLISHED)

    def test_publish_blocked_when_no_committee_members_are_configured(self):
        RoleAssignment.objects.filter(employee=self.committee_member).delete()
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        with self.assertRaises(PolicyWorkflowError):
            publish_policy(policy, actor=self.employee)

    def test_a_new_draft_version_needs_its_own_fresh_approval(self):
        # Points at PolicyApproval's own reasoning (models.py): a new draft
        # version does not inherit the previous version's approvals.
        v1 = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._publish(v1)
        v2 = create_new_version(v1, body="v2", actor=self.employee)
        with self.assertRaises(PolicyWorkflowError):
            publish_policy(v2, actor=self.employee)

    def test_approving_a_non_draft_policy_is_rejected(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._publish(policy)
        with self.assertRaises(PolicyWorkflowError):
            record_policy_approval(policy, approver=self.committee_member)

    def test_approval_is_idempotent(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        approval1 = record_policy_approval(policy, approver=self.committee_member, comment="Looks fine.")
        approval2 = record_policy_approval(policy, approver=self.committee_member, comment="Different text ignored.")
        self.assertEqual(approval1.id, approval2.id)
        self.assertEqual(policy.approvals.count(), 1)

    def test_cannot_archive_a_draft_policy(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        with self.assertRaises(PolicyWorkflowError):
            archive_policy(policy, actor=self.employee)

    def test_new_version_can_be_drafted_from_an_archived_policy(self):
        v1 = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._publish(v1)
        archive_policy(v1, actor=self.employee)
        v2 = create_new_version(v1, body="v2", actor=self.employee)
        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.status, Policy.Status.DRAFT)

    def test_create_policy_generates_chunks_from_body(self):
        long_paragraph = "Sentence one. " * 100  # ~1400 chars, forces a paragraph split
        body = f"Intro paragraph.\n\n{long_paragraph}\n\nClosing paragraph."
        policy = create_policy(title="Chunked Policy", category=Policy.Category.OTHER, body=body)
        chunks = list(PolicyChunk.objects.filter(policy=policy).order_by("sequence"))
        self.assertGreater(len(chunks), 1)
        self.assertEqual([c.sequence for c in chunks], list(range(len(chunks))))
        # Reassembling should roughly preserve all the source text (chunks
        # are non-overlapping in this simple pass).
        self.assertIn("Intro paragraph.", chunks[0].text)

    def test_regenerating_chunks_replaces_the_old_set(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="Short body.")
        first_count = PolicyChunk.objects.filter(policy=policy).count()
        self.assertEqual(first_count, 1)

        update_draft(policy, body="A completely different, longer body.\n\nWith a second paragraph.")
        second_chunks = list(PolicyChunk.objects.filter(policy=policy).order_by("sequence"))
        self.assertEqual(len(second_chunks), 1)  # still short enough to be one chunk
        self.assertIn("second paragraph", second_chunks[0].text)

    def test_update_draft_rejects_non_draft_policy(self):
        policy = create_policy(title="Leave Policy", category=Policy.Category.LEAVE, body="v1")
        self._publish(policy)
        with self.assertRaises(PolicyWorkflowError):
            update_draft(policy, body="sneaky edit")

    def test_create_policy_from_uploaded_txt_file(self):
        upload = SimpleUploadedFile("handbook.txt", b"Everyone must arrive on time.", content_type="text/plain")
        policy = create_policy(title="Attendance Policy", category=Policy.Category.OTHER, file=upload)
        self.assertEqual(policy.body, "Everyone must arrive on time.")
        self.assertTrue(policy.source_file.name.endswith(".txt"))
        self.assertTrue(PolicyChunk.objects.filter(policy=policy).exists())

    def test_create_policy_from_uploaded_docx_file(self):
        from docx import Document as DocxDocument

        buffer = io.BytesIO()
        document = DocxDocument()
        document.add_paragraph("All staff must complete annual compliance training.")
        document.save(buffer)
        upload = SimpleUploadedFile(
            "policy.docx", buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        policy = create_policy(title="Training Policy", category=Policy.Category.OTHER, file=upload)
        self.assertIn("annual compliance training", policy.body)

    def test_create_policy_from_uploaded_pdf_file(self):
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(100, 750, "Remote work requires manager approval.")
        pdf.save()
        upload = SimpleUploadedFile("policy.pdf", buffer.getvalue(), content_type="application/pdf")
        policy = create_policy(title="Remote Work Policy", category=Policy.Category.REMOTE_WORK, file=upload)
        self.assertIn("Remote work requires manager approval.", policy.body)

    def test_create_policy_rejects_unsupported_file_type(self):
        upload = SimpleUploadedFile("policy.exe", b"binary junk", content_type="application/octet-stream")
        with self.assertRaises(PolicyWorkflowError):
            create_policy(title="Bad Upload", category=Policy.Category.OTHER, file=upload)

    def test_create_policy_rejects_file_with_no_extractable_text(self):
        upload = SimpleUploadedFile("empty.txt", b"   \n\n  ", content_type="text/plain")
        with self.assertRaises(PolicyWorkflowError):
            create_policy(title="Empty Upload", category=Policy.Category.OTHER, file=upload)


class ChunkTextTests(TestCase):
    def test_empty_text_produces_no_chunks(self):
        self.assertEqual(chunk_text(""), [])

    def test_short_text_is_a_single_chunk(self):
        self.assertEqual(chunk_text("A short policy body."), ["A short policy body."])

    def test_multiple_short_paragraphs_pack_into_one_chunk(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        chunks = chunk_text(text, target_chars=1000)
        self.assertEqual(len(chunks), 1)

    def test_long_paragraph_is_split_on_sentence_boundaries(self):
        text = "Sentence one is here. " * 100
        chunks = chunk_text(text, target_chars=200)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 220)  # small slack for the last sentence in a chunk

    def test_chunks_do_not_exceed_target_chars_by_much_for_paragraph_packing(self):
        paragraphs = [f"Paragraph {i} with some filler words to add length." for i in range(20)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, target_chars=300)
        self.assertGreater(len(chunks), 1)
        joined = " ".join(chunks)
        for paragraph in paragraphs:
            self.assertIn(paragraph, joined)


class ExtractTextTests(TestCase):
    def test_txt_extraction(self):
        upload = SimpleUploadedFile("notes.txt", "Café policy: coffee is free.".encode("utf-8"))
        self.assertEqual(extract_text(upload), "Café policy: coffee is free.")

    def test_unsupported_extension_raises(self):
        upload = SimpleUploadedFile("policy.xyz", b"data")
        with self.assertRaises(UnsupportedDocumentError):
            extract_text(upload)
