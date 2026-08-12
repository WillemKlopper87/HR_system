from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import Feedback, Goal, Review, ReviewCycle
from .services import launch_review_cycle

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class PerformanceApiTestCase(TestCase):
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


class ReviewCyclePermissionTests(PerformanceApiTestCase):
    def test_any_authenticated_employee_can_list_cycles(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get("/api/v1/review-cycles/")
        self.assertEqual(response.status_code, 200)

    def test_non_hr_admin_cannot_create_cycle(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/review-cycles/", {"name": "X", "start_date": "2026-01-01", "end_date": "2026-12-31"}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_launch_and_close_cycle(self):
        cycle = ReviewCycle.objects.create(name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        self.client.force_authenticate(user=self.hr_admin.user)

        launch_response = self.client.post(f"/api/v1/review-cycles/{cycle.id}/launch/")
        self.assertEqual(launch_response.status_code, 200)
        self.assertEqual(launch_response.data["status"], "launched")
        self.assertGreater(launch_response.data["reviews_created"], 0)

        close_response = self.client.post(f"/api/v1/review-cycles/{cycle.id}/close/")
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(close_response.data["status"], "closed")

    def test_completion_stats(self):
        cycle = ReviewCycle.objects.create(name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        launch_review_cycle(cycle)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/review-cycles/{cycle.id}/completion/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["completed"], 0)
        self.assertGreater(response.data["total"], 0)


class ReviewRowScopeAndWriteGatingTests(PerformanceApiTestCase):
    def setUp(self):
        super().setUp()
        self.cycle = ReviewCycle.objects.create(name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
        launch_review_cycle(self.cycle)
        self.review = Review.objects.get(review_cycle=self.cycle, employee=self.report)

    def test_outsider_cannot_view_review(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get(f"/api/v1/reviews/{self.review.id}/")
        self.assertEqual(response.status_code, 403)

    def test_reviewee_can_write_self_section_only(self):
        self.client.force_authenticate(user=self.report.user)
        ok = self.client.patch(
            f"/api/v1/reviews/{self.review.id}/", {"self_rating": 3, "self_comments": "ok"}, format="json"
        )
        self.assertEqual(ok.status_code, 200)
        blocked = self.client.patch(f"/api/v1/reviews/{self.review.id}/", {"manager_rating": 5}, format="json")
        self.assertEqual(blocked.status_code, 400)

    def test_manager_can_write_manager_section_only(self):
        self.client.force_authenticate(user=self.manager.user)
        ok = self.client.patch(
            f"/api/v1/reviews/{self.review.id}/", {"manager_rating": 4, "manager_comments": "good"}, format="json"
        )
        self.assertEqual(ok.status_code, 200)
        blocked = self.client.patch(f"/api/v1/reviews/{self.review.id}/", {"self_rating": 1}, format="json")
        self.assertEqual(blocked.status_code, 400)

    def test_submit_self_requires_rating_set_first(self):
        self.client.force_authenticate(user=self.report.user)
        premature = self.client.post(f"/api/v1/reviews/{self.review.id}/submit_self/")
        self.assertEqual(premature.status_code, 400)

        self.client.patch(f"/api/v1/reviews/{self.review.id}/", {"self_rating": 3}, format="json")
        response = self.client.post(f"/api/v1/reviews/{self.review.id}/submit_self/")
        self.assertEqual(response.status_code, 200)
        self.review.refresh_from_db()
        self.assertIsNotNone(self.review.self_submitted_at)

    def test_only_assigned_manager_can_submit_manager_review(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        # hr_admin is authorized to reach the object at all (row-scope=all),
        # but isn't the review's own recorded manager, so the submit action
        # itself must still reject — row-scope access and "is the assigned
        # reviewer" are different checks.
        response = self.client.post(f"/api/v1/reviews/{self.review.id}/submit_manager/")
        self.assertEqual(response.status_code, 403)


class GoalPermissionTests(PerformanceApiTestCase):
    def test_outsider_cannot_create_goal_for_report(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.post("/api/v1/goals/", {"employee": self.report.id, "title": "X"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_manager_can_create_goal_for_report(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/goals/", {"employee": self.report.id, "manager": self.manager.id, "title": "Ship X"}, format="json"
        )
        self.assertEqual(response.status_code, 201)

    def test_employee_can_create_own_goal(self):
        self.client.force_authenticate(user=self.report.user)
        response = self.client.post("/api/v1/goals/", {"employee": self.report.id, "title": "Learn Y"}, format="json")
        self.assertEqual(response.status_code, 201)

    def test_outsider_does_not_see_report_goal_in_list(self):
        Goal.objects.create(employee=self.report, title="Private goal")
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get("/api/v1/goals/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_employee_query_param_filters_to_one_employees_goals(self):
        Goal.objects.create(employee=self.report, title="Report's goal")
        Goal.objects.create(employee=self.manager, title="Manager's own goal")
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/goals/?employee={self.report.id}")
        self.assertEqual(response.status_code, 200)
        titles = {row["title"] for row in response.data["results"]}
        self.assertEqual(titles, {"Report's goal"})


class FeedbackApiTests(PerformanceApiTestCase):
    def test_any_authenticated_employee_can_create_peer_feedback(self):
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.post(
            "/api/v1/feedback/", {"employee": self.report.id, "text": "Great collaborator"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["feedback_type"], "peer")
        self.assertEqual(response.data["author"], self.outsider.id)

    def test_manager_feedback_classified_automatically(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(
            "/api/v1/feedback/", {"employee": self.report.id, "text": "Strong quarter"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["feedback_type"], "manager")

    def test_outsider_cannot_read_feedback_about_report(self):
        Feedback.objects.create(employee=self.report, author=self.manager, feedback_type="manager", text="x")
        self.client.force_authenticate(user=self.outsider.user)
        response = self.client.get("/api/v1/feedback/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_reviewee_can_read_own_feedback(self):
        Feedback.objects.create(employee=self.report, author=self.manager, feedback_type="manager", text="x")
        self.client.force_authenticate(user=self.report.user)
        response = self.client.get("/api/v1/feedback/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
