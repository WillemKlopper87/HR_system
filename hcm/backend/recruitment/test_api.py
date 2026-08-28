from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from establishment.models import Position
from rbac_audit.models import ConsentRecord, Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Applicant, BackgroundCheck, InterviewScorecard, InterviewSession, Offer, Requisition
from .services import transition_applicant

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class RecruitmentApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        self.recruiter = Employee.objects.hire(
            employee_number="R001", first_name="Rita", last_name="Recruiter", date_of_birth=date(1985, 1, 1),
            work_email="rita@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="rita", password="x"),
        )
        RoleAssignment.objects.create(employee=self.recruiter, role=Role.objects.get(name="recruiter"))

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1980, 1, 1),
            work_email="hradmin@example.com", hire_date=date(2018, 1, 1), department=self.dept,
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

        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN, opened_at=date(2026, 7, 1),
        )
        self.applicant = Applicant.objects.create(
            requisition=self.requisition, first_name="Alex", last_name="Applicant",
            email="alex@example.com", date_of_birth=date(1995, 3, 3),
        )


class RequisitionPermissionTests(RecruitmentApiTestCase):
    def test_plain_employee_cannot_view_requisitions(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/requisitions/")
        self.assertEqual(response.status_code, 403)

    def test_recruiter_can_create_and_view_requisitions(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get("/api/v1/requisitions/")
        self.assertEqual(response.status_code, 200)

        # Predates Task 6's establishment-control validation (Sprint 4-5,
        # commit 787fcd3) -- a position is now required to link on create.
        position = Position.objects.create(
            post_number="P-00002", title="Frontend Engineer", department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            status=Position.Status.APPROVED,
        )
        response = self.client.post(
            "/api/v1/requisitions/",
            {
                "title": "Frontend Engineer", "department": self.dept.id, "occupational_level": self.level.id,
                "job_grade": self.grade.id, "location": self.location.id, "headcount": 1,
                "status": Requisition.Status.OPEN, "positions": [position.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_by"], self.recruiter.id)
        # opened_at auto-stamped when status is OPEN
        self.assertIsNotNone(response.data["opened_at"])


class ApplicantConsentGatingTests(RecruitmentApiTestCase):
    def test_setting_demographics_without_consent_is_rejected(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.patch(
            f"/api/v1/applicants/{self.applicant.id}/", {"race": "african"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_setting_demographics_after_consent_succeeds(self):
        self.client.force_authenticate(user=self.recruiter.user)
        consent_response = self.client.post(f"/api/v1/applicants/{self.applicant.id}/consent/")
        self.assertEqual(consent_response.status_code, 201)

        response = self.client.patch(
            f"/api/v1/applicants/{self.applicant.id}/", {"race": "african", "gender": "female"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["race"], "african")

    def test_demographics_hidden_from_read_without_consent(self):
        self.applicant.race = "african"
        self.applicant.save(update_fields=["race"])
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get(f"/api/v1/applicants/{self.applicant.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("race", response.data)
        self.assertFalse(response.data["has_demographic_consent"])

    def test_demographics_visible_after_consent(self):
        self.applicant.race = "african"
        self.applicant.save(update_fields=["race"])
        from rbac_audit.consent import record_consent

        record_consent(
            applicant=self.applicant, purpose=ConsentRecord.Purpose.DEMOGRAPHIC_SELF_ID,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1", actor=self.recruiter,
        )
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get(f"/api/v1/applicants/{self.applicant.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["race"], "african")
        self.assertTrue(response.data["has_demographic_consent"])


class ApplicantTransitionApiTests(RecruitmentApiTestCase):
    def test_invalid_transition_returns_400(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post(
            f"/api/v1/applicants/{self.applicant.id}/transition/", {"to_stage": "hired"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_full_pipeline_to_hire_creates_employee(self):
        self.client.force_authenticate(user=self.recruiter.user)
        for stage in ["screened", "interview", "offer", "hired"]:
            response = self.client.post(
                f"/api/v1/applicants/{self.applicant.id}/transition/", {"to_stage": stage}, format="json"
            )
            self.assertEqual(response.status_code, 200, response.data)

        self.applicant.refresh_from_db()
        self.assertIsNotNone(self.applicant.resulting_employee)
        self.assertTrue(Employee.objects.filter(work_email="alex@example.com").exists())


class OfferApprovalTests(RecruitmentApiTestCase):
    def setUp(self):
        super().setUp()
        self.offer = Offer.objects.create(
            applicant=self.applicant, proposed_job_grade=self.grade, proposed_annual_salary="450000.00",
            proposed_by=self.recruiter,
        )

    def test_proposer_cannot_approve_own_offer(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post(f"/api/v1/offers/{self.offer.id}/approve/")
        self.assertEqual(response.status_code, 400)

    def test_different_approver_can_approve(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/offers/{self.offer.id}/approve/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "approved")
        self.assertEqual(response.data["approved_by"], self.hr_admin.id)

    def test_cannot_accept_unapproved_offer(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post(f"/api/v1/offers/{self.offer.id}/accept/")
        self.assertEqual(response.status_code, 400)


class RecruitmentDashboardTests(RecruitmentApiTestCase):
    def test_non_recruiter_cannot_view_dashboard(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/dashboards/recruitment/")
        self.assertEqual(response.status_code, 403)

    def test_dashboard_returns_pipeline_and_suppression_flag(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get("/api/v1/dashboards/recruitment/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("by_stage", response.data)
        self.assertEqual(response.data["total_applicants"], 1)
        self.assertEqual(response.data["open_requisitions"], 1)
        # recruiter holds an ALL-scope role with S-tier read -> unsuppressed
        self.assertFalse(response.data["small_cell_suppression_applied"])


class RecruitmentFunnelTests(RecruitmentApiTestCase):
    """A rejected applicant's furthest stage must still count (current_stage
    alone would collapse them to 'rejected' and erase real progress) --
    the whole reason the funnel is derived from ApplicantStageEvent."""

    def setUp(self):
        super().setUp()
        self.applicant.race = "african"
        self.applicant.save(update_fields=["race"])
        transition_applicant(self.applicant, to_stage=Applicant.Stage.SCREENED, actor=self.recruiter)
        transition_applicant(self.applicant, to_stage=Applicant.Stage.INTERVIEW, actor=self.recruiter)
        transition_applicant(self.applicant, to_stage=Applicant.Stage.REJECTED, actor=self.recruiter)

        other_requisition = Requisition.objects.create(
            title="Other Role", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN,
        )
        self.other_applicant = Applicant.objects.create(
            requisition=other_requisition, first_name="Sam", last_name="Second",
            email="sam@example.com", date_of_birth=date(1994, 2, 2), race="white",
        )
        transition_applicant(self.other_applicant, to_stage=Applicant.Stage.SCREENED, actor=self.recruiter)

    def test_non_recruiter_cannot_view_funnel(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/dashboards/recruitment/funnel/")
        self.assertEqual(response.status_code, 403)

    def test_rejected_applicant_still_counted_at_furthest_stage_reached(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get("/api/v1/dashboards/recruitment/funnel/")
        self.assertEqual(response.status_code, 200)
        by_race = {row["stage"]: row for row in response.data["by_race"]}
        # Both applicants reached "applied" and "screened".
        self.assertEqual(by_race["applied"]["total"], 2)
        self.assertEqual(by_race["screened"]["total"], 2)
        # Only the rejected applicant made it to "interview"; the other
        # never left "screened".
        self.assertEqual(by_race["interview"]["total"], 1)
        self.assertEqual(by_race["offer"]["total"], 0)
        self.assertEqual(by_race["hired"]["total"], 0)
        african_at_interview = next(r for r in by_race["interview"]["breakdown"] if r["key"] == "african")
        self.assertEqual(african_at_interview["count"], 1)

    def test_funnel_uses_demographics_at_stage_entry(self):
        self.applicant.race = "coloured"
        self.applicant.save(update_fields=["race"])

        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get("/api/v1/dashboards/recruitment/funnel/")

        self.assertEqual(response.status_code, 200)
        interview = next(row for row in response.data["by_race"] if row["stage"] == "interview")
        self.assertEqual(interview["breakdown"], [{"key": "african", "count": 1, "suppressed": False}])

    def test_department_filter_narrows_the_funnel(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get(f"/api/v1/dashboards/recruitment/funnel/?department={self.dept.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_applicants"], 2)

        other_dept = Department.objects.create(name="Finance", code="FIN")
        response = self.client.get(f"/api/v1/dashboards/recruitment/funnel/?department={other_dept.id}")
        self.assertEqual(response.data["total_applicants"], 0)


class RequisitionPositionValidationApiTests(RecruitmentApiTestCase):
    def setUp(self):
        super().setUp()
        self.position = Position.objects.create(
            post_number="P-00001", title="Agent", department=self.dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )

    def test_create_without_positions_is_rejected(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/requisitions/", {
            "title": "X", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id, "headcount": 1, "status": "open",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("positions", response.data)

    def test_create_with_matching_approved_vacant_position_succeeds(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/requisitions/", {
            "title": "X", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id, "headcount": 1, "status": "open",
            "positions": [self.position.id],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_create_with_a_position_from_another_department_is_rejected(self):
        """Proves the serializer actually threads the requisition's own
        department/location into validate_requisition_positions -- on
        create there is no instance for it to read them off."""
        other_dept = Department.objects.create(name="Finance", code="FIN")
        foreign = Position.objects.create(
            post_number="P-00002", title="Analyst", department=other_dept, occupational_level=self.level,
            job_grade=self.grade, location=self.location, status=Position.Status.APPROVED,
        )
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/requisitions/", {
            "title": "X", "department": self.dept.id, "occupational_level": self.level.id,
            "job_grade": self.grade.id, "location": self.location.id, "headcount": 1, "status": "open",
            "positions": [foreign.id],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("different department", str(response.data["positions"]))

    def test_status_only_patch_on_a_requisition_with_no_positions_succeeds(self):
        """Requisitions that predate establishment control (and the two in
        the demo seed data) have zero linked positions, and the only
        requisition-mutation UI is a status-only PATCH. Enforcing
        "at least one position" on a write that isn't touching `positions`
        would lock every such requisition out of ever changing status
        again. Only writes that actually supply `positions` -- and
        creations, which always must -- are held to that bar."""
        self.assertEqual(self.requisition.positions.count(), 0)
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.patch(
            f"/api/v1/requisitions/{self.requisition.id}/",
            {"status": Requisition.Status.ON_HOLD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.requisition.refresh_from_db()
        self.assertEqual(self.requisition.status, Requisition.Status.ON_HOLD)

    def test_patch_that_does_supply_an_empty_positions_list_is_still_rejected(self):
        """The grandfather clause is narrow: deliberately clearing the
        positions of a requisition IS a write to `positions`, so it stays
        rejected -- otherwise a client could empty a linked requisition and
        break the headcount/positions invariant the whole feature rests on."""
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.patch(
            f"/api/v1/requisitions/{self.requisition.id}/", {"positions": []}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("positions", response.data)


def _hire_employee(dept, level, grade, location, *, number, first, last, email, username):
    return Employee.objects.hire(
        employee_number=number, first_name=first, last_name=last, date_of_birth=date(1988, 5, 5),
        work_email=email, hire_date=date(2019, 1, 1), department=dept, occupational_level=level,
        job_grade=grade, location=location, user=User.objects.create_user(username=username, password="x"),
    )


class InterviewSchedulingApiTestCase(RecruitmentApiTestCase):
    """Base for InterviewSession/InterviewScorecard tests: two interviewer
    employees (holding no recruitment-module role at all -- being tapped as
    a panelist is a row-level, ad-hoc assignment, not tied to a role) and
    the shared applicant moved to the 'interview' stage."""

    def setUp(self):
        super().setUp()
        self.interviewer1 = _hire_employee(
            self.dept, self.level, self.grade, self.location,
            number="E200", first="Ivy", last="Interviewer", email="ivy@example.com", username="ivy",
        )
        self.interviewer2 = _hire_employee(
            self.dept, self.level, self.grade, self.location,
            number="E201", first="Ian", last="Panelist", email="ian@example.com", username="ian",
        )
        transition_applicant(self.applicant, to_stage=Applicant.Stage.SCREENED, actor=self.recruiter)
        transition_applicant(self.applicant, to_stage=Applicant.Stage.INTERVIEW, actor=self.recruiter)


class InterviewSessionApiTests(InterviewSchedulingApiTestCase):
    def test_scheduling_requires_applicant_at_interview_stage(self):
        not_ready = Applicant.objects.create(
            requisition=self.requisition, first_name="Not", last_name="Ready",
            email="notready@example.com", date_of_birth=date(1990, 1, 1),
        )
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/interview-sessions/", {
            "applicant": not_ready.id, "scheduled_at": "2026-09-01T10:00:00Z",
            "interviewers": [self.interviewer1.id],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("applicant", response.data)

    def test_at_least_one_interviewer_required(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/interview-sessions/", {
            "applicant": self.applicant.id, "scheduled_at": "2026-09-01T10:00:00Z", "interviewers": [],
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("interviewers", response.data)

    def test_recruiter_can_schedule_session_with_narrow_applicant_summary(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/interview-sessions/", {
            "applicant": self.applicant.id, "scheduled_at": "2026-09-01T10:00:00Z", "round_number": 1,
            "location": "Boardroom 2", "interviewers": [self.interviewer1.id, self.interviewer2.id],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        summary = response.data["applicant_summary"]
        self.assertEqual(summary["first_name"], "Alex")
        self.assertEqual(summary["current_stage"], "interview")
        # Deliberately narrow -- no demographics, no email/phone/date_of_birth.
        self.assertNotIn("race", summary)
        self.assertNotIn("email", summary)
        self.assertNotIn("date_of_birth", summary)

    def test_plain_employee_with_no_panel_membership_sees_empty_list(self):
        session = InterviewSession.objects.create(applicant=self.applicant, scheduled_at="2026-09-01T10:00:00Z")
        session.interviewers.set([self.interviewer1])
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/interview-sessions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_non_panel_employee_cannot_retrieve_directly(self):
        """interviewer2 holds no recruitment role and isn't on THIS
        session's panel -- get_queryset's row-filtering excludes it before
        object-level permissions are even checked, so this is a 404 (object
        not in their filtered queryset), not a 403 -- same "filtered out,
        not merely permission-denied" shape succession's own self-exclusion
        uses."""
        session = InterviewSession.objects.create(applicant=self.applicant, scheduled_at="2026-09-01T10:00:00Z")
        session.interviewers.set([self.interviewer1])
        self.client.force_authenticate(user=self.interviewer2.user)
        response = self.client.get(f"/api/v1/interview-sessions/{session.id}/")
        self.assertEqual(response.status_code, 404)

    def test_mine_only_scopes_even_a_recruiter_to_their_own_panel_assignments(self):
        """A recruiter who is ALSO occasionally a panelist needs "my
        interviews" to mean their own assignments, not the admin view of
        every session in the system -- role alone can't decide this, hence
        the explicit ?mine=true query param."""
        own_session = InterviewSession.objects.create(applicant=self.applicant, scheduled_at="2026-09-01T10:00:00Z")
        own_session.interviewers.set([self.recruiter, self.interviewer1])
        other_applicant = Applicant.objects.create(
            requisition=self.requisition, first_name="Other", last_name="Applicant",
            email="other@example.com", date_of_birth=date(1992, 1, 1),
        )
        transition_applicant(other_applicant, to_stage=Applicant.Stage.SCREENED, actor=self.recruiter)
        transition_applicant(other_applicant, to_stage=Applicant.Stage.INTERVIEW, actor=self.recruiter)
        InterviewSession.objects.create(
            applicant=other_applicant, scheduled_at="2026-09-02T10:00:00Z"
        ).interviewers.set([self.interviewer1])

        self.client.force_authenticate(user=self.recruiter.user)
        everything = self.client.get("/api/v1/interview-sessions/")
        self.assertEqual(len(everything.data["results"]), 2)

        mine = self.client.get("/api/v1/interview-sessions/?mine=true")
        self.assertEqual(len(mine.data["results"]), 1)
        self.assertEqual(mine.data["results"][0]["id"], own_session.id)

    def test_assigned_interviewer_can_read_but_not_write_own_session(self):
        session = InterviewSession.objects.create(applicant=self.applicant, scheduled_at="2026-09-01T10:00:00Z")
        session.interviewers.set([self.interviewer1])
        self.client.force_authenticate(user=self.interviewer1.user)

        read = self.client.get(f"/api/v1/interview-sessions/{session.id}/")
        self.assertEqual(read.status_code, 200)

        write = self.client.patch(f"/api/v1/interview-sessions/{session.id}/", {"notes": "x"}, format="json")
        self.assertEqual(write.status_code, 403)


class InterviewScorecardApiTests(InterviewSchedulingApiTestCase):
    def setUp(self):
        super().setUp()
        self.session = InterviewSession.objects.create(applicant=self.applicant, scheduled_at="2026-09-01T10:00:00Z")
        self.session.interviewers.set([self.interviewer1, self.interviewer2])

    def _submit(self, user, *, rating=4, recommendation="hire", extra=None):
        self.client.force_authenticate(user=user)
        payload = {
            "session": self.session.id, "skill_rating": rating, "communication_rating": rating,
            "culture_fit_rating": rating, "comments": "Solid.", "recommendation": recommendation,
        }
        payload.update(extra or {})
        return self.client.post("/api/v1/interview-scorecards/", payload, format="json")

    def test_non_panel_employee_cannot_submit(self):
        response = self._submit(self.plain_employee.user)
        self.assertEqual(response.status_code, 400)
        self.assertIn("session", response.data)

    def test_interviewer_field_is_forced_server_side_not_client_supplied(self):
        response = self._submit(self.interviewer1.user, extra={"interviewer": self.interviewer2.id})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["interviewer"], self.interviewer1.id)

    def test_duplicate_scorecard_for_same_session_rejected(self):
        first = self._submit(self.interviewer1.user)
        self.assertEqual(first.status_code, 201, first.data)
        second = self._submit(self.interviewer1.user)
        self.assertEqual(second.status_code, 400)

    def test_blind_review_hides_peer_score_until_own_submitted(self):
        submitted = self._submit(self.interviewer1.user, rating=5, recommendation="strong_hire")
        self.assertEqual(submitted.status_code, 201, submitted.data)

        self.client.force_authenticate(user=self.interviewer2.user)
        before = self.client.get("/api/v1/interview-scorecards/")
        self.assertEqual(before.status_code, 200)
        peer_row = next(r for r in before.data["results"] if r["interviewer"] == self.interviewer1.id)
        self.assertNotIn("recommendation", peer_row)
        self.assertNotIn("skill_rating", peer_row)
        self.assertNotIn("comments", peer_row)
        # Existence is still visible -- only content is masked.
        self.assertEqual(peer_row["session"], self.session.id)

        own = self._submit(self.interviewer2.user, rating=3, recommendation="hire")
        self.assertEqual(own.status_code, 201, own.data)

        after = self.client.get("/api/v1/interview-scorecards/")
        peer_row_after = next(r for r in after.data["results"] if r["interviewer"] == self.interviewer1.id)
        self.assertEqual(peer_row_after["recommendation"], "strong_hire")
        self.assertEqual(peer_row_after["skill_rating"], 5)

    def test_recruiter_always_sees_full_detail_without_submitting_own(self):
        self._submit(self.interviewer1.user, rating=5, recommendation="strong_hire")
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.get("/api/v1/interview-scorecards/")
        self.assertEqual(response.status_code, 200)
        row = response.data["results"][0]
        self.assertIn("recommendation", row)
        self.assertEqual(row["recommendation"], "strong_hire")

    def test_non_panel_employee_sees_no_scorecards_at_all(self):
        self._submit(self.interviewer1.user, rating=5, recommendation="strong_hire")
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/interview-scorecards/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_not_even_hr_admin_can_author_on_anothers_behalf(self):
        """No proxy-entry (design spec §2.2) -- hr_admin can READ every
        scorecard but creating one always attributes to the authenticated
        actor, and hr_admin isn't an assigned interviewer on this session at
        all, so a create attempt is rejected the same way plain_employee's is."""
        response = self._submit(self.hr_admin.user)
        self.assertEqual(response.status_code, 400)
        self.assertIn("session", response.data)


class BackgroundCheckApiTests(RecruitmentApiTestCase):
    def test_recruiter_can_create_and_requested_by_is_forced_server_side(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.post("/api/v1/background-checks/", {
            "applicant": self.applicant.id, "check_type": "reference", "status": "requested",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["requested_by"], self.recruiter.id)

    def test_status_can_move_non_monotonically(self):
        """No ALLOWED_TRANSITIONS state machine (unlike Applicant.Stage) --
        a flagged result can legitimately be revised to cleared after a
        documented review (design spec §2.3)."""
        self.client.force_authenticate(user=self.hr_admin.user)
        check = BackgroundCheck.objects.create(
            applicant=self.applicant, check_type=BackgroundCheck.CheckType.CRIMINAL_RECORD,
            status=BackgroundCheck.Status.FLAGGED,
        )
        response = self.client.patch(
            f"/api/v1/background-checks/{check.id}/",
            {"status": "cleared", "notes": "False-positive name match, verified with SAPS."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "cleared")

    def test_plain_employee_forbidden(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/background-checks/")
        self.assertEqual(response.status_code, 403)

    def test_assigned_interviewer_has_no_access_at_all(self):
        """Unlike InterviewSession/InterviewScorecard, an interviewer gets
        nothing here -- background-check outcomes are exactly the kind of
        thing an interviewer forming their own independent impression
        should not see (design spec §2.3)."""
        interviewer = _hire_employee(
            self.dept, self.level, self.grade, self.location,
            number="E202", first="Ivy", last="Interviewer", email="ivy2@example.com", username="ivy2",
        )
        session = InterviewSession.objects.create(applicant=self.applicant, scheduled_at="2026-09-01T10:00:00Z")
        session.interviewers.set([interviewer])
        self.client.force_authenticate(user=interviewer.user)
        response = self.client.get("/api/v1/background-checks/")
        self.assertEqual(response.status_code, 403)


class RequisitionExternalPostingFieldTests(RecruitmentApiTestCase):
    def test_external_posting_defaults_false(self):
        self.assertFalse(self.requisition.external_posting)

    def test_recruiter_can_flag_a_requisition_externally_postable(self):
        self.client.force_authenticate(user=self.recruiter.user)
        response = self.client.patch(
            f"/api/v1/requisitions/{self.requisition.id}/",
            {"external_posting": True, "description": "Great team, great work."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["external_posting"])
        self.assertEqual(response.data["description"], "Great team, great work.")
