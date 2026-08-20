from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from establishment.models import Position
from rbac_audit.models import ConsentRecord, Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Applicant, Offer, Requisition

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
