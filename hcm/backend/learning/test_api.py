from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Certification, EmployeeSkill, Skill, TrainingRecord

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class LearningApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        self.hr_admin = Employee.objects.hire(
            employee_number="HR1", first_name="HR", last_name="Admin", date_of_birth=date(1980, 1, 1),
            work_email="hr@example.com", hire_date=date(2015, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="hr", password="x"),
        )
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))

        self.manager = Employee.objects.hire(
            employee_number="MGR", first_name="Mandy", last_name="Manager", date_of_birth=date(1980, 1, 1),
            work_email="mgr@example.com", hire_date=date(2015, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="mgr", password="x"),
        )
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="line_manager"))
        RoleAssignment.objects.create(employee=self.manager, role=Role.objects.get(name="employee"))

        self.report = Employee.objects.hire(
            employee_number="E100", first_name="Rep", last_name="Ort", date_of_birth=date(1995, 1, 1),
            work_email="rep@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, manager=self.manager,
            user=User.objects.create_user(username="rep", password="x"),
        )
        RoleAssignment.objects.create(employee=self.report, role=Role.objects.get(name="employee"))

        self.outsider = Employee.objects.hire(
            employee_number="OUT", first_name="Out", last_name="Sider", date_of_birth=date(1990, 1, 1),
            work_email="outsider@example.com", hire_date=date(2019, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="out", password="x"),
        )
        RoleAssignment.objects.create(employee=self.outsider, role=Role.objects.get(name="employee"))

        self.skill = Skill.objects.create(name="Python", category=Skill.Category.TECHNICAL)


class SkillCatalogPermissionTests(LearningApiTestCase):
    def test_any_authenticated_employee_can_read_catalog(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get("/api/v1/skills/")
        self.assertEqual(response.status_code, 200)

    def test_non_hr_admin_cannot_create_skill(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post("/api/v1/skills/", {"name": "New Skill"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_create_skill(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post("/api/v1/skills/", {"name": "New Skill", "category": "soft"}, format="json")
        self.assertEqual(response.status_code, 201)


class EmployeeSkillTests(LearningApiTestCase):
    def test_outsider_cannot_add_skill_for_report(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.post(
            "/api/v1/employee-skills/", {"employee": self.report.id, "skill": self.skill.id}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_manager_can_add_skill_for_report(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/employee-skills/",
            {"employee": self.report.id, "skill": self.skill.id, "proficiency": "advanced"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_duplicate_skill_entry_is_rejected(self):
        EmployeeSkill.objects.create(employee=self.report, skill=self.skill)
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/employee-skills/", {"employee": self.report.id, "skill": self.skill.id}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_outsider_does_not_see_report_skills_in_list(self):
        EmployeeSkill.objects.create(employee=self.report, skill=self.skill)
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get("/api/v1/employee-skills/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_employee_query_param_filters_to_one_employee(self):
        other_skill = Skill.objects.create(name="Go", category=Skill.Category.TECHNICAL)
        EmployeeSkill.objects.create(employee=self.report, skill=self.skill)
        EmployeeSkill.objects.create(employee=self.manager, skill=other_skill)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/employee-skills/?employee={self.report.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["skill"], self.skill.id)


class CertificationAndTrainingRecordTests(LearningApiTestCase):
    def test_employee_can_add_own_certification(self):
        self.client.force_authenticate(user=self.report.user)
        response = self.client.post(
            "/api/v1/certifications/", {"employee": self.report.id, "name": "AWS SA"}, format="json"
        )
        self.assertEqual(response.status_code, 201)

    def test_outsider_cannot_add_training_record_for_report(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.post(
            "/api/v1/training-records/", {"employee": self.report.id, "title": "Course"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_manager_can_add_training_record_for_report(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/training-records/",
            {"employee": self.report.id, "title": "AWS Bootcamp", "status": "completed", "hours": "40.0"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)


class TrainingRecordEnrollmentRequestApiTests(LearningApiTestCase):
    """Sprint 15 (ESS): learning enrollment requests — a self-submission is
    always forced to REQUESTED regardless of what the client sends, and the
    requester can't later self-approve it."""

    def test_self_submission_forces_requested_status_and_strips_hours_cost(self):
        self.client.force_authenticate(user=self.report.user)
        response = self.client.post(
            "/api/v1/training-records/",
            {
                "employee": self.report.id, "title": "Advanced Kubernetes", "provider": "A Cloud Guru",
                "status": "completed", "hours": "40.0", "cost": "9999.00",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "requested")
        self.assertIsNone(response.data["hours"])
        self.assertIsNone(response.data["cost"])

    def test_manager_submission_for_report_is_not_forced_to_requested(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/training-records/",
            {"employee": self.report.id, "title": "AWS Bootcamp", "status": "planned"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "planned")

    def test_self_cannot_edit_status_hours_cost_on_own_request(self):
        self.client.force_authenticate(user=self.report.user)
        create = self.client.post(
            "/api/v1/training-records/", {"employee": self.report.id, "title": "Advanced Kubernetes"}, format="json"
        )
        record_id = create.data["id"]
        response = self.client.patch(
            f"/api/v1/training-records/{record_id}/", {"status": "planned"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_self_can_still_edit_title_on_own_pending_request(self):
        self.client.force_authenticate(user=self.report.user)
        create = self.client.post(
            "/api/v1/training-records/", {"employee": self.report.id, "title": "Advanced Kubernetes"}, format="json"
        )
        record_id = create.data["id"]
        response = self.client.patch(
            f"/api/v1/training-records/{record_id}/", {"title": "Advanced Kubernetes & Helm"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_manager_can_approve_a_report_request(self):
        self.client.force_authenticate(user=self.report.user)
        create = self.client.post(
            "/api/v1/training-records/", {"employee": self.report.id, "title": "Advanced Kubernetes"}, format="json"
        )
        record_id = create.data["id"]
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.patch(
            f"/api/v1/training-records/{record_id}/", {"status": "planned"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "planned")


class SkillsInventoryTests(LearningApiTestCase):
    def test_non_hr_admin_cannot_view_inventory(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/learning/skills-inventory/")
        self.assertEqual(response.status_code, 403)

    def test_inventory_breaks_down_by_department_and_level(self):
        EmployeeSkill.objects.create(employee=self.report, skill=self.skill)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/learning/skills-inventory/")
        self.assertEqual(response.status_code, 200)
        row = next(s for s in response.data["skills"] if s["skill"] == "Python")
        self.assertEqual(row["total_holders"], 1)
        self.assertEqual(row["by_department"], [{"key": "Engineering", "count": 1}])


class TeamDevelopmentTests(LearningApiTestCase):
    def test_manager_sees_own_team_rollup(self):
        EmployeeSkill.objects.create(employee=self.report, skill=self.skill)
        TrainingRecord.objects.create(employee=self.report, title="Course", status=TrainingRecord.Status.COMPLETED)
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/learning/team-development/")
        self.assertEqual(response.status_code, 200)
        report_row = next(e for e in response.data["employees"] if e["employee_number"] == "E100")
        self.assertEqual(report_row["skill_count"], 1)
        self.assertEqual(report_row["completed_training_count"], 1)
        employee_numbers = {e["employee_number"] for e in response.data["employees"]}
        self.assertNotIn("OUT", employee_numbers)


class WspAtrExportTests(LearningApiTestCase):
    def setUp(self):
        super().setUp()
        TrainingRecord.objects.create(
            employee=self.report, title="AWS Bootcamp", status=TrainingRecord.Status.COMPLETED,
            hours="40.0", cost="5000.00", completion_date=date(2026, 3, 1),
        )

    def test_non_hr_admin_cannot_export(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/dashboards/learning/wsp-atr-export/")
        self.assertEqual(response.status_code, 403)

    def test_export_is_csv_with_expected_columns_and_row(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/learning/wsp-atr-export/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode()
        self.assertIn("record_type,employee_number,occupational_level,race,gender,disability_status", content)
        self.assertIn("E100", content)
        self.assertIn("training,E100", content)
        self.assertIn("AWS Bootcamp", content)
        self.assertIn("5000.00", content)

    def test_year_filter_excludes_other_years(self):
        TrainingRecord.objects.create(
            employee=self.report, title="Old Course", status=TrainingRecord.Status.COMPLETED,
            completion_date=date(2024, 5, 1),
        )
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/learning/wsp-atr-export/?year=2026")
        content = response.content.decode()
        self.assertIn("AWS Bootcamp", content)
        self.assertNotIn("Old Course", content)

    def test_certifications_are_unioned_in_as_qualification_rows(self):
        """C2 design spec §2.4: Certification wasn't in this export at all
        before — now it's unioned in with a record_type discriminator."""
        Certification.objects.create(
            employee=self.report, name="BCom Accounting", issuing_body="UNISA", issue_date=date(2026, 2, 1),
        )
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/learning/wsp-atr-export/")
        content = response.content.decode()
        self.assertIn("qualification,E100", content)
        self.assertIn("BCom Accounting", content)
        self.assertIn("UNISA", content)

    def test_certification_year_filter_uses_issue_date(self):
        Certification.objects.create(
            employee=self.report, name="Old Diploma", issuing_body="TUT", issue_date=date(2020, 1, 1),
        )
        Certification.objects.create(
            employee=self.report, name="New Diploma", issuing_body="TUT", issue_date=date(2026, 1, 1),
        )
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/learning/wsp-atr-export/?year=2026")
        content = response.content.decode()
        self.assertIn("New Diploma", content)
        self.assertNotIn("Old Diploma", content)
