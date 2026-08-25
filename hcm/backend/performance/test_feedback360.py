"""360 feedback (C6, design spec 2026-08-25-performance-calibration-360-
design.md). Reuses ReviewTestCase's fixture -- self.employee reports to
self.head; self.other and self.delegate are unrelated peers a priori.
"""
from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model

from core_hr.models import Employee
from rbac_audit.models import Role, RoleAssignment

from .models.feedback360 import Feedback360Rater, Feedback360Request, Feedback360Response
from .services import AgreementWorkflowError
from .services.feedback360 import (
    aggregate_for,
    approve_rater,
    classify_relationship,
    close_request,
    decline_rater,
    nominate_rater,
    open_request,
    submit_response,
    withdraw_rater,
)
from .test_agreements import PASSWORD
from .test_reviews import ReviewTestCase

User = get_user_model()


class Feedback360TestCase(ReviewTestCase):
    def _hire_report(self, number, first, last, username, manager):
        return Employee.objects.hire(
            employee_number=number, first_name=first, last_name=last, date_of_birth=date(1990, 1, 1),
            work_email=f"{username}@sentech.example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, manager=manager,
            user=User.objects.create_user(username=username, password=PASSWORD),
        )


class ClassifyRelationshipTests(Feedback360TestCase):
    def test_relationship_derivation(self):
        agreement = self._agreed()
        report = self._hire_report("E060", "Direct", "Report", "directreport1", manager=self.employee)
        self.assertEqual(classify_relationship(self.employee, agreement), Feedback360Rater.Relationship.SELF)
        self.assertEqual(classify_relationship(self.head, agreement), Feedback360Rater.Relationship.MANAGER)
        self.assertEqual(classify_relationship(report, agreement), Feedback360Rater.Relationship.DIRECT_REPORT)
        self.assertEqual(classify_relationship(self.other, agreement), Feedback360Rater.Relationship.PEER)


class OpenRequestTests(Feedback360TestCase):
    def test_opening_creates_automatic_self_and_manager_slots(self):
        agreement = self._agreed()
        request = open_request(agreement, actor=self.hr_admin)
        slots = {s.rater_id: s for s in request.raters.all()}
        self.assertEqual(slots[self.employee.id].relationship, Feedback360Rater.Relationship.SELF)
        self.assertEqual(slots[self.employee.id].status, Feedback360Rater.Status.APPROVED)
        self.assertEqual(slots[self.head.id].relationship, Feedback360Rater.Relationship.MANAGER)
        self.assertEqual(slots[self.head.id].status, Feedback360Rater.Status.APPROVED)

    def test_cannot_open_before_contracting_is_agreed(self):
        agreement = self._agreement()  # DRAFT, from AgreementTestCase
        with self.assertRaises(AgreementWorkflowError):
            open_request(agreement, actor=self.hr_admin)


class NominationTests(Feedback360TestCase):
    def setUp(self):
        super().setUp()
        self.agreement = self._agreed()
        self.request = open_request(self.agreement, actor=self.hr_admin)

    def test_subject_can_nominate_a_peer(self):
        slot = nominate_rater(self.request, self.other, actor=self.employee)
        self.assertEqual(slot.relationship, Feedback360Rater.Relationship.PEER)
        self.assertEqual(slot.status, Feedback360Rater.Status.PENDING_APPROVAL)

    def test_head_can_nominate_a_direct_report_of_the_subject(self):
        report = self._hire_report("E061", "Direct", "Report", "directreport2", manager=self.employee)
        slot = nominate_rater(self.request, report, actor=self.head)
        self.assertEqual(slot.relationship, Feedback360Rater.Relationship.DIRECT_REPORT)

    def test_unrelated_third_party_cannot_nominate(self):
        self._login(self.other)
        response = self.client.post(
            "/api/v1/feedback-360-raters/", {"request": self.request.id, "rater": self.delegate.id}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_cannot_nominate_self_or_manager_again(self):
        with self.assertRaises(AgreementWorkflowError):
            nominate_rater(self.request, self.employee, actor=self.employee)
        with self.assertRaises(AgreementWorkflowError):
            nominate_rater(self.request, self.head, actor=self.employee)

    def test_cannot_nominate_the_same_person_twice(self):
        nominate_rater(self.request, self.other, actor=self.employee)
        with self.assertRaises(AgreementWorkflowError):
            nominate_rater(self.request, self.other, actor=self.employee)

    def test_only_head_or_hr_admin_can_approve(self):
        slot = nominate_rater(self.request, self.other, actor=self.employee)
        self._login(self.employee)
        response = self.client.post(f"/api/v1/feedback-360-raters/{slot.id}/approve/")
        self.assertEqual(response.status_code, 403)

        self._login(self.head)
        response = self.client.post(f"/api/v1/feedback-360-raters/{slot.id}/approve/")
        self.assertEqual(response.status_code, 200)
        slot.refresh_from_db()
        self.assertEqual(slot.status, Feedback360Rater.Status.APPROVED)

    def test_decline_a_nomination(self):
        slot = nominate_rater(self.request, self.other, actor=self.employee)
        decline_rater(slot, actor=self.head)
        slot.refresh_from_db()
        self.assertEqual(slot.status, Feedback360Rater.Status.DECLINED_NOMINATION)

    def test_withdraw_before_responding_but_not_after(self):
        slot = approve_rater(nominate_rater(self.request, self.other, actor=self.employee), actor=self.head)
        withdraw_rater(slot, actor=self.other)
        slot.refresh_from_db()
        self.assertEqual(slot.status, Feedback360Rater.Status.WITHDRAWN)

        slot2 = approve_rater(nominate_rater(self.request, self.delegate, actor=self.employee), actor=self.head)
        submit_response(
            slot2, actor=self.delegate, collaboration_rating=4, communication_rating=4, reliability_rating=4,
        )
        with self.assertRaises(AgreementWorkflowError):
            withdraw_rater(slot2, actor=self.delegate)


class ResponseSubmissionTests(Feedback360TestCase):
    def setUp(self):
        super().setUp()
        self.agreement = self._agreed()
        self.request = open_request(self.agreement, actor=self.hr_admin)
        self.peer_slot = approve_rater(nominate_rater(self.request, self.other, actor=self.employee), actor=self.head)

    def test_only_the_named_rater_can_submit(self):
        with self.assertRaises(AgreementWorkflowError):
            submit_response(
                self.peer_slot, actor=self.head, collaboration_rating=4, communication_rating=4,
                reliability_rating=4,
            )

    def test_cannot_respond_before_approval(self):
        pending = nominate_rater(self.request, self.delegate, actor=self.employee)
        with self.assertRaises(AgreementWorkflowError):
            submit_response(
                pending, actor=self.delegate, collaboration_rating=3, communication_rating=3, reliability_rating=3,
            )

    def test_api_respond_action(self):
        self._login(self.other)
        response = self.client.post(
            f"/api/v1/feedback-360-raters/{self.peer_slot.id}/respond/",
            {
                "collaboration_rating": 5, "communication_rating": 4, "reliability_rating": 4,
                "strengths": "Always reliable in a crunch.", "development_areas": "Could delegate more.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(Feedback360Response.objects.filter(rater_slot=self.peer_slot).exists())

    def test_cannot_respond_once_the_round_is_closed(self):
        close_request(self.request, actor=self.hr_admin)
        with self.assertRaises(AgreementWorkflowError):
            submit_response(
                self.peer_slot, actor=self.other, collaboration_rating=4, communication_rating=4,
                reliability_rating=4,
            )


class VisibilityTests(Feedback360TestCase):
    """The load-bearing decision (spec §2.10): full attribution to Head/
    hr_admin/auditor and to a rater's own row; self/manager attributed to
    the subject; peer/direct_report never individually shown to the subject,
    aggregate-only once >=3 responses exist."""

    def setUp(self):
        super().setUp()
        self.agreement = self._agreed()
        self.request = open_request(self.agreement, actor=self.hr_admin)
        self.self_slot = self.request.raters.get(relationship=Feedback360Rater.Relationship.SELF)
        self.manager_slot = self.request.raters.get(relationship=Feedback360Rater.Relationship.MANAGER)
        submit_response(
            self.self_slot, actor=self.employee, collaboration_rating=4, communication_rating=4,
            reliability_rating=3, strengths="Self-assessment strengths text.",
        )
        submit_response(
            self.manager_slot, actor=self.head, collaboration_rating=3, communication_rating=4,
            reliability_rating=4, development_areas="Manager development note.",
        )
        self.peer_slot = approve_rater(nominate_rater(self.request, self.other, actor=self.employee), actor=self.head)
        submit_response(
            self.peer_slot, actor=self.other, collaboration_rating=5, communication_rating=5,
            reliability_rating=5, strengths="Peer says great collaborator.",
        )

    def _get(self, viewer):
        self._login(viewer)
        response = self.client.get(f"/api/v1/feedback-360-requests/{self.request.id}/")
        self.assertEqual(response.status_code, 200, response.data)
        return {r["rater"]: r for r in response.data["raters"]}

    def test_head_sees_everything_attributed(self):
        raters = self._get(self.head)
        self.assertIsNotNone(raters[self.other.id]["response"])
        self.assertEqual(raters[self.other.id]["response"]["strengths"], "Peer says great collaborator.")

    def test_hr_admin_sees_everything_attributed(self):
        raters = self._get(self.hr_admin)
        self.assertIsNotNone(raters[self.other.id]["response"])

    def test_auditor_sees_everything_attributed(self):
        auditor = self._hire("AUD3", "Ivy", "Auditor", "ivyaud3")
        RoleAssignment.objects.create(employee=auditor, role=Role.objects.get(name="auditor"))
        raters = self._get(auditor)
        self.assertIsNotNone(raters[self.other.id]["response"])

    def test_subject_sees_self_and_manager_attributed(self):
        raters = self._get(self.employee)
        self.assertIsNotNone(raters[self.employee.id]["response"])
        self.assertIsNotNone(raters[self.head.id]["response"])

    def test_subject_never_sees_the_individual_peer_response(self):
        raters = self._get(self.employee)
        self.assertIsNone(raters[self.other.id]["response"])

    def test_rater_sees_their_own_response_via_the_rater_slot_not_the_whole_request(self):
        # A plain peer with no other tie to the agreement cannot view the
        # whole Feedback360Request (spec §5.2 -- same audience as the parent
        # agreement, which they're not part of); their own slot is reachable
        # through the rater endpoint instead (spec §5.3), and it carries
        # their own response in full.
        self._login(self.other)
        whole_request = self.client.get(f"/api/v1/feedback-360-requests/{self.request.id}/")
        # Object-permission denial on a detail route reads as 404, not 403
        # (views_agreements.py::_HideForbiddenAsNotFound, reused here so a
        # denial can't confirm a request's existence to someone with no tie
        # to it).
        self.assertEqual(whole_request.status_code, 404)

        own_slot = self.client.get(f"/api/v1/feedback-360-raters/{self.peer_slot.id}/")
        self.assertEqual(own_slot.status_code, 200)
        self.assertIsNotNone(own_slot.data["response"])
        self.assertEqual(own_slot.data["response"]["strengths"], "Peer says great collaborator.")

    def test_aggregate_hidden_below_the_response_floor(self):
        self.assertIsNone(aggregate_for(self.request, Feedback360Rater.Relationship.PEER))
        # peer_aggregate lives on the request payload, not per-rater.
        self._login(self.employee)
        response = self.client.get(f"/api/v1/feedback-360-requests/{self.request.id}/")
        self.assertIsNone(response.data["peer_aggregate"])

    def test_aggregate_appears_once_three_peer_responses_exist_and_never_carries_free_text(self):
        for i, name in enumerate(["Delta", "Echo"], start=1):
            peer = self._hire(f"E07{i}", name, "Peer", f"peer{i}")
            slot = approve_rater(nominate_rater(self.request, peer, actor=self.employee), actor=self.head)
            submit_response(
                slot, actor=peer, collaboration_rating=3, communication_rating=3, reliability_rating=3,
                strengths="Should never reach the subject.",
            )

        aggregate = aggregate_for(self.request, Feedback360Rater.Relationship.PEER)
        self.assertIsNotNone(aggregate)
        self.assertEqual(aggregate["response_count"], 3)
        self.assertNotIn("strengths", aggregate)
        self.assertNotIn("development_areas", aggregate)

        self._login(self.employee)
        response = self.client.get(f"/api/v1/feedback-360-requests/{self.request.id}/")
        self.assertIsNotNone(response.data["peer_aggregate"])
        self.assertEqual(response.data["peer_aggregate"]["response_count"], 3)
        # Still never individually attributed, even now.
        raters = {r["rater"]: r for r in response.data["raters"]}
        self.assertIsNone(raters[self.other.id]["response"])

    def test_unrelated_employee_with_no_tie_at_all_cannot_read_the_request(self):
        stranger = self._hire("E080", "Stranger", "Danger", "strangerdanger")
        self._login(stranger)
        response = self.client.get(f"/api/v1/feedback-360-requests/{self.request.id}/")
        self.assertEqual(response.status_code, 404)  # _HideForbiddenAsNotFound

    def test_a_peer_rater_can_still_reach_their_own_slot_via_the_rater_list(self):
        # `other` cannot view the whole request (asserted implicitly above via
        # masking) but their own slot is reachable through the rater endpoint
        # even without agreement-level access, per spec §5.2/§5.3.
        self._login(self.other)
        response = self.client.get(f"/api/v1/feedback-360-raters/?request={self.request.id}")
        self.assertEqual(response.status_code, 200)
        ids = [r["id"] for r in response.data["results"]]
        self.assertEqual(ids, [self.peer_slot.id])
