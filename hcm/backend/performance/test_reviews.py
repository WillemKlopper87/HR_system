"""PC-2: mid-year (Q2) and final (Q4) reviews, evidence, scoring, hr_attention,
legacy Review derivation.

Reuses AgreementTestCase's fixture from PC-1 (employee/head/delegate/hr_admin,
a published two-KPI template) and its contracting-flow helper to reach an
AGREED agreement, then drives it through Q2 and Q4 the same way two real
people would: open the phase, edit while it's open, sign employee-then-Head.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from core_hr.test_utils import read_streaming_response
from django.core.files.uploadedfile import SimpleUploadedFile
from rbac_audit.models import Role, RoleAssignment

from .models import (
    EvidenceItem,
    PerformanceAgreement,
    PeriodPhase,
)
from .models.cycles import Review, ReviewCycle
from .services import (
    AgreementWorkflowError,
    amend_agreement,
    approve_agreement,
    create_agreement,
    open_phase,
    sign_agreement,
    submit_agreement,
)
from .test_agreements import PASSWORD, AgreementTestCase


class ReviewTestCase(AgreementTestCase):
    """Extends PC-1's fixture with a FINAL phase (the base fixture only
    configures contracting + mid-year) and a helper to reach AGREED — the
    common starting point for every Q2/Q4 test below."""

    def setUp(self):
        super().setUp()
        PeriodPhase.objects.create(
            period=self.period, stage=PeriodPhase.Stage.FINAL, opens_on=date(2027, 4, 1), due_on=date(2027, 4, 30)
        )

    def _agreed(self, *, employee=None, weights=None):
        employee = employee or self.employee
        agreement = create_agreement(period=self.period, employee=employee, template=self.template)
        if weights is not None:
            for element, weight in zip(agreement.elements.all(), weights):
                element.weight = weight
                element.save()
        submit_agreement(agreement, actor=employee)
        approve_agreement(agreement, actor=self.head)
        sign_agreement(agreement, actor=employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        return agreement

    def _open_midyear(self, agreement):
        open_phase(self.period, PeriodPhase.Stage.MIDYEAR)
        agreement.refresh_from_db()
        return agreement

    def _open_final(self, agreement):
        open_phase(self.period, PeriodPhase.Stage.FINAL)
        agreement.refresh_from_db()
        return agreement

    def _rate_all(self, agreement, rating):
        for element in agreement.elements.all():
            element.final_rating = rating
            element.save()


class MidyearReviewTests(ReviewTestCase):
    def test_opening_midyear_moves_only_agreed_agreements(self):
        agreed = self._agreed()
        still_draft_employee = self._hire("E010", "Still", "Draft", "stilldraft", manager=self.head)
        create_agreement(period=self.period, employee=still_draft_employee, template=self.template)

        open_phase(self.period, PeriodPhase.Stage.MIDYEAR)
        agreed.refresh_from_db()
        self.assertEqual(agreed.status, PerformanceAgreement.Status.MIDYEAR_OPEN)
        untouched = PerformanceAgreement.objects.get(employee=still_draft_employee)
        self.assertEqual(untouched.status, PerformanceAgreement.Status.DRAFT)

    def test_q2_fields_editable_only_while_midyear_open(self):
        agreement = self._agreed()
        element = agreement.elements.first()
        self._login(self.employee)

        too_early = self.client.patch(
            f"/api/v1/agreement-elements/{element.id}/", {"q2_employee_comment": "too early"}, format="json"
        )
        self.assertEqual(too_early.status_code, 400)
        self.assertIn("can only be edited while", str(too_early.data).lower())

        self._open_midyear(agreement)
        opened = self.client.patch(
            f"/api/v1/agreement-elements/{element.id}/",
            {"q2_target_note": "On track for R1m", "q2_employee_comment": "Pipeline looks solid"},
            format="json",
        )
        self.assertEqual(opened.status_code, 200, opened.data)
        element.refresh_from_db()
        self.assertEqual(element.q2_employee_comment, "Pipeline looks solid")

    def test_head_comment_stays_editable_after_the_employee_signs(self):
        # The Head reviews and comments *after* the employee has signed, but
        # before signing themself -- their own field (only their own field)
        # must stay open through MIDYEAR_EMPLOYEE_SIGNED.
        agreement = self._agreed()
        element = agreement.elements.first()
        self._open_midyear(agreement)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.MIDYEAR_EMPLOYEE_SIGNED)

        self._login(self.head)
        head_comment = self.client.patch(
            f"/api/v1/agreement-elements/{element.id}/",
            {"q2_head_comment": "Agreed, good progress"},
            format="json",
        )
        self.assertEqual(head_comment.status_code, 200, head_comment.data)
        element.refresh_from_db()
        self.assertEqual(element.q2_head_comment, "Agreed, good progress")

        # the employee's own field is locked once they've signed, even for the Head
        locked = self.client.patch(
            f"/api/v1/agreement-elements/{element.id}/",
            {"q2_employee_comment": "trying to sneak an edit in"},
            format="json",
        )
        self.assertEqual(locked.status_code, 400)
        self.assertIn("can only be edited while", str(locked.data).lower())

    def test_employee_then_head_sign_midyear_in_order(self):
        agreement = self._agreed()
        self._open_midyear(agreement)

        # the stage is open, but the employee hasn't signed yet -- the Head
        # jumping the queue gets the order error, not "nothing is open".
        with self.assertRaisesMessage(AgreementWorkflowError, "The employee signs first"):
            sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)

        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.MIDYEAR_EMPLOYEE_SIGNED)

        with self.assertRaisesMessage(AgreementWorkflowError, "Only the Head"):
            # a third party (not the Head, not a delegate) can never sign as Head
            sign_agreement(agreement, actor=self.other, role="head", password=PASSWORD)

        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.MIDYEAR_SIGNED)
        # a second document/signature pair exists for this stage, distinct from contracting
        self.assertEqual(agreement.documents.filter(stage="midyear").count(), 1)
        self.assertEqual(agreement.signatures.filter(stage="midyear").count(), 2)
        self.assertEqual(agreement.signatures.filter(stage="contracting").count(), 2)

    def test_signing_midyear_before_it_opens_is_refused(self):
        agreement = self._agreed()
        with self.assertRaisesMessage(AgreementWorkflowError, "nothing open"):
            sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)


class FinalReviewTests(ReviewTestCase):
    def test_final_opens_directly_from_agreed_when_midyear_is_never_opened(self):
        # open_phase() acts period-wide, so "skips mid-year" only makes sense
        # as "this org never opened the mid-year phase at all this year" --
        # not as a per-employee choice (see the MIDYEAR_SIGNED sibling test
        # below for the "mid-year genuinely happened" path).
        agreement = self._agreed()
        open_phase(self.period, PeriodPhase.Stage.FINAL)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.FINAL_OPEN)

    def test_final_opens_from_midyear_signed_when_midyear_happened(self):
        agreement = self._agreed()
        open_phase(self.period, PeriodPhase.Stage.MIDYEAR)
        agreement.refresh_from_db()
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.MIDYEAR_SIGNED)

        open_phase(self.period, PeriodPhase.Stage.FINAL)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.FINAL_OPEN)

    def test_final_rating_editable_only_while_final_open(self):
        agreement = self._agreed()
        element = agreement.elements.first()
        self._login(self.employee)

        too_early = self.client.patch(
            f"/api/v1/agreement-elements/{element.id}/", {"final_rating": 4}, format="json"
        )
        self.assertEqual(too_early.status_code, 400)

        self._open_final(agreement)
        opened = self.client.patch(
            f"/api/v1/agreement-elements/{element.id}/", {"final_rating": 4}, format="json"
        )
        self.assertEqual(opened.status_code, 200, opened.data)
        element.refresh_from_db()
        self.assertEqual(element.final_rating, 4)

    def test_final_head_comment_stays_editable_after_the_employee_signs(self):
        agreement = self._agreed()
        element = agreement.elements.first()
        self._open_final(agreement)
        self._rate_all(agreement, 4)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.FINAL_EMPLOYEE_SIGNED)

        self._login(self.head)
        head_comment = self.client.patch(
            f"/api/v1/agreement-elements/{element.id}/",
            {"final_head_comment": "Agreed with the self-assessment"},
            format="json",
        )
        self.assertEqual(head_comment.status_code, 200, head_comment.data)
        element.refresh_from_db()
        self.assertEqual(element.final_head_comment, "Agreed with the self-assessment")

        # the rating is locked once the employee has signed, even for the Head
        locked = self.client.patch(
            f"/api/v1/agreement-elements/{element.id}/", {"final_rating": 2}, format="json"
        )
        self.assertEqual(locked.status_code, 400)

    def test_final_signature_requires_every_kpi_rated(self):
        agreement = self._agreed()
        self._open_final(agreement)
        elements = list(agreement.elements.all())
        elements[0].final_rating = 4
        elements[0].save()
        # elements[1] left unrated
        with self.assertRaisesMessage(AgreementWorkflowError, "Every KPI needs a rating"):
            sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)

    def test_scoring_is_the_weighted_sum_of_ratings(self):
        agreement = self._agreed(weights=[Decimal("0.4"), Decimal("0.6")])
        self._open_final(agreement)
        elements = list(agreement.elements.all())
        elements[0].final_rating = 4  # 0.4 * 4 = 1.6
        elements[0].save()
        elements[1].final_rating = 5  # 0.6 * 5 = 3.0
        elements[1].save()

        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.FINAL_SIGNED)
        self.assertEqual(agreement.final_score, Decimal("4.60"))
        self.assertFalse(agreement.hr_attention)

    def test_hr_attention_set_when_overall_score_below_threshold(self):
        agreement = self._agreed(weights=[Decimal("0.5"), Decimal("0.5")])
        self._open_final(agreement)
        self._rate_all(agreement, 2)  # overall = 2.0 < default threshold 3.00
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertEqual(agreement.final_score, Decimal("2.00"))
        self.assertTrue(agreement.hr_attention)
        self.assertIn("below", agreement.hr_attention_reason)

    def test_hr_attention_set_for_a_single_low_kpi_even_if_overall_is_fine(self):
        agreement = self._agreed(weights=[Decimal("0.1"), Decimal("0.9")])
        self._open_final(agreement)
        elements = list(agreement.elements.all())
        elements[0].final_rating = 1  # dragged down, but tiny weight
        elements[0].save()
        elements[1].final_rating = 5
        elements[1].save()
        # overall = 0.1*1 + 0.9*5 = 4.6, comfortably above threshold -- but KPI 1 itself is a 1
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertGreaterEqual(agreement.final_score, Decimal("3.00"))
        self.assertTrue(agreement.hr_attention)
        self.assertIn("KPI rating below", agreement.hr_attention_reason)

    def test_no_attention_flag_when_everything_is_on_target_or_better(self):
        agreement = self._agreed()
        self._open_final(agreement)
        self._rate_all(agreement, 3)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertFalse(agreement.hr_attention)
        self.assertEqual(agreement.hr_attention_reason, "")

    def test_legacy_review_is_derived_once_final_is_signed(self):
        from .models.cycles import ReviewCycle as _RC

        cycle = _RC.objects.create(
            name="2026/27 (legacy mirror)", cycle_type=_RC.CycleType.ANNUAL, start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
        )
        self.period.legacy_cycle = cycle
        self.period.save(update_fields=["legacy_cycle"])

        agreement = self._agreed()
        self._open_final(agreement)
        self._rate_all(agreement, 4)
        self.assertFalse(Review.objects.filter(review_cycle=cycle, employee=self.employee).exists())

        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        self.assertFalse(Review.objects.filter(review_cycle=cycle, employee=self.employee).exists())
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)

        review = Review.objects.get(review_cycle=cycle, employee=self.employee)
        self.assertEqual(review.self_rating, 4)
        self.assertEqual(review.manager_rating, 4)
        self.assertEqual(review.manager, self.head)
        self.assertIsNotNone(review.self_submitted_at)
        self.assertIsNotNone(review.manager_submitted_at)

    def test_no_legacy_cycle_means_no_review_is_created_and_nothing_breaks(self):
        self.assertIsNone(self.period.legacy_cycle_id)
        agreement = self._agreed()
        self._open_final(agreement)
        self._rate_all(agreement, 4)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        self.assertEqual(Review.objects.filter(employee=self.employee).count(), 0)

    def test_amendment_from_final_signed_bumps_revision_and_reopens_contracting(self):
        agreement = self._agreed()
        self._open_final(agreement)
        self._rate_all(agreement, 4)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        self.assertEqual(agreement.status, PerformanceAgreement.Status.FINAL_SIGNED)

        amend_agreement(agreement, actor=self.head, reason="Restructure moved this KPA to another division")
        agreement.refresh_from_db()
        self.assertEqual(agreement.revision, 2)
        self.assertEqual(agreement.status, PerformanceAgreement.Status.DRAFT)
        # rev-1 signatures/scores survive as history, not wiped
        self.assertEqual(agreement.signatures.filter(revision=1).count(), 4)  # 2 contracting + 2 final


class EvidenceTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.agreement = self._agreed()
        self._open_final(self.agreement)
        self._rate_all(self.agreement, 4)
        self.element = self.agreement.elements.first()

    def _upload(self, actor, **overrides):
        self._login(actor)
        payload = {"element": self.element.id, "kind": "file", "description": "Sales report"}
        payload.update(overrides)
        if "file" not in payload and payload.get("kind") == "file":
            payload["file"] = SimpleUploadedFile("evidence.txt", b"Q4 revenue tracking sheet", content_type="text/plain")
        return self.client.post("/api/v1/agreement-evidence/", payload, format="multipart")

    def test_upload_file_hashes_and_is_downloadable_by_the_uploader(self):
        response = self._upload(self.employee)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["sha256"]), 64)
        self.assertIsNotNone(response.data["download_url"])

        download = self.client.get(response.data["download_url"])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(read_streaming_response(download), b"Q4 revenue tracking sheet")

    def test_file_content_must_match_a_supported_evidence_type(self):
        # a renamed binary that isn't PDF/image/Office/text -- the sniff, not
        # the filename, is what's checked (KPI-Contracting-Investigation.md
        # §6 "sniffed"; mirrors policies/extraction.py's "sniff first" rule).
        bad = self._upload(
            self.employee,
            file=SimpleUploadedFile("evidence.pdf", bytes([0x00, 0x01, 0x02, 0x03] * 10), content_type="application/pdf"),
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn("doesn't match a supported evidence type", str(bad.data))

        real_pdf = self._upload(
            self.employee,
            file=SimpleUploadedFile("evidence.pdf", b"%PDF-1.4\n%mock pdf content", content_type="application/pdf"),
        )
        self.assertEqual(real_pdf.status_code, 201, real_pdf.data)

    def test_file_evidence_is_capped_at_20mb(self):
        oversized = SimpleUploadedFile("big.txt", b"a" * (20 * 1024 * 1024 + 1), content_type="text/plain")
        response = self._upload(self.employee, file=oversized)
        self.assertEqual(response.status_code, 400)
        self.assertIn("capped at 20 MB", str(response.data))

    def test_link_evidence_requires_https(self):
        self._login(self.employee)
        bad = self.client.post(
            "/api/v1/agreement-evidence/",
            {"element": self.element.id, "kind": "link", "url": "http://example.com/report.xlsx"},
            format="multipart",
        )
        self.assertEqual(bad.status_code, 400)
        good = self.client.post(
            "/api/v1/agreement-evidence/",
            {"element": self.element.id, "kind": "link", "url": "https://sentech.sharepoint.com/report.xlsx"},
            format="multipart",
        )
        self.assertEqual(good.status_code, 201, good.data)
        self.assertIsNone(good.data["download_url"])

    def test_element_reports_has_evidence(self):
        self._login(self.employee)
        before = self.client.get(f"/api/v1/agreement-elements/{self.element.id}/")
        self.assertFalse(before.data["has_evidence"])
        self._upload(self.employee)
        after = self.client.get(f"/api/v1/agreement-elements/{self.element.id}/")
        self.assertTrue(after.data["has_evidence"])
        self.assertEqual(len(after.data["evidence_items"]), 1)

    def test_evidence_is_optional_by_default(self):
        # no evidence uploaded at all -- still allowed to sign off (default template)
        self.assertFalse(self.agreement.template.evidence_required)
        sign_agreement(self.agreement, actor=self.employee, role="employee", password=PASSWORD)  # does not raise

    def test_evidence_required_template_blocks_signature_without_evidence(self):
        self.agreement.template.evidence_required = True
        self.agreement.template.save(update_fields=["evidence_required"])
        with self.assertRaisesMessage(AgreementWorkflowError, "requires evidence"):
            sign_agreement(self.agreement, actor=self.employee, role="employee", password=PASSWORD)

    def test_evidence_required_template_passes_once_evidence_exists(self):
        self.agreement.template.evidence_required = True
        self.agreement.template.save(update_fields=["evidence_required"])
        for element in self.agreement.elements.all():
            EvidenceItem.objects.create(
                element=element, stage="final", kind="link", url="https://example.sharepoint.com/x",
                uploaded_by=self.employee,
            )
        sign_agreement(self.agreement, actor=self.employee, role="employee", password=PASSWORD)  # does not raise

    def test_evidence_cannot_be_deleted_once_the_stage_is_signed_off(self):
        response = self._upload(self.employee)
        evidence_id = response.data["id"]
        # deletable pre-signoff
        self._login(self.employee)
        ok = self.client.delete(f"/api/v1/agreement-evidence/{evidence_id}/")
        self.assertEqual(ok.status_code, 204)

        response2 = self._upload(self.employee)
        evidence_id2 = response2.data["id"]
        sign_agreement(self.agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(self.agreement, actor=self.head, role="head", password=PASSWORD)

        self._login(self.head)
        blocked = self.client.delete(f"/api/v1/agreement-evidence/{evidence_id2}/")
        self.assertEqual(blocked.status_code, 403)

    def test_evidence_added_after_signoff_is_stamped(self):
        response = self._upload(self.employee)
        self.assertFalse(response.data["added_after_signoff"])

        sign_agreement(self.agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(self.agreement, actor=self.head, role="head", password=PASSWORD)

        late = self._upload(self.head, description="Found this after signing")
        self.assertEqual(late.status_code, 201, late.data)
        self.assertTrue(late.data["added_after_signoff"])

    def test_auditor_can_read_but_not_upload_evidence(self):
        auditor = self._hire("AUD1", "Ivy", "Auditor", "ivyauditor")
        RoleAssignment.objects.create(employee=auditor, role=Role.objects.get(name="auditor"))
        self._upload(self.employee)
        self._login(auditor)
        listing = self.client.get(f"/api/v1/agreement-evidence/?element={self.element.id}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data["results"]), 1)
        blocked = self.client.post(
            "/api/v1/agreement-evidence/",
            {"element": self.element.id, "kind": "link", "url": "https://example.com/x"},
            format="multipart",
        )
        self.assertEqual(blocked.status_code, 403)
