"""API-level role gating for onboarding/offboarding checklists (design
spec section 7). Service-layer/state-machine behaviour is covered in
test_checklists.py; this file is specifically "who may call which
endpoint" -- same split core_hr/test_exits.py and core_hr/test_api.py use
between the two files."""
from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from rbac_audit.models import Role, RoleAssignment

from .models import ChecklistTemplate, ChecklistTemplateItem
from .services import complete_item, create_checklist_instance, create_template, publish_template

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Support", code="SUP-CL")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="SC1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="SCHO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class ChecklistAPITestCase(TestCase):
    def setUp(self):
        dept, level, grade, location = _seed_reference_data()

        def make(number, role_name=None, manager=None):
            employee = Employee.objects.hire(
                employee_number=number, first_name=number, last_name="Test", date_of_birth=date(1985, 1, 1),
                work_email=f"{number.lower()}@example.com", hire_date=date(2015, 1, 1), department=dept,
                occupational_level=level, job_grade=grade, location=location, manager=manager,
                user=User.objects.create_user(username=number.lower(), password="x"),
            )
            RoleAssignment.objects.create(employee=employee, role=Role.objects.get(name="employee"))
            if role_name:
                RoleAssignment.objects.create(employee=employee, role=Role.objects.get(name=role_name))
            return employee

        self.hr_admin = make("APIHRA1", "hr_admin")
        self.auditor = make("APIAUD1", "auditor")
        self.manager = make("APIMGR1", "line_manager")
        self.report = make("APIRPT1", manager=self.manager)
        self.outsider_manager = make("APIMGR2", "line_manager")
        self.outsider_report = make("APIRPT2", manager=self.outsider_manager)

        self.template = create_template(
            name="API onboarding", direction=ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin,
            items=[
                {"label": "HR task", "owner_role": ChecklistTemplateItem.OwnerRole.HR},
                {"label": "Manager task", "owner_role": ChecklistTemplateItem.OwnerRole.LINE_MANAGER},
                {"label": "IT task", "owner_role": ChecklistTemplateItem.OwnerRole.IT},
            ],
        )
        publish_template(self.template, actor=self.hr_admin)
        self.instance = create_checklist_instance(self.report, self.template, actor=self.hr_admin)

        self.client = APIClient()


class TemplateAccessTests(ChecklistAPITestCase):
    def test_hr_admin_can_read_and_create_templates(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/checklist-templates/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/v1/checklist-templates/", {
            "name": "New template", "direction": "onboarding",
        })
        self.assertEqual(response.status_code, 201, response.data)

    def test_auditor_can_read_but_not_create_templates(self):
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get("/api/v1/checklist-templates/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/v1/checklist-templates/", {
            "name": "New template", "direction": "onboarding",
        })
        self.assertEqual(response.status_code, 403)

    def test_line_manager_and_employee_cannot_read_templates(self):
        for actor in (self.manager, self.report):
            self.client.force_authenticate(user=actor.user)
            response = self.client.get("/api/v1/checklist-templates/")
            self.assertEqual(response.status_code, 403)

    def test_publish_action_is_hr_admin_only(self):
        draft = create_template(name="To publish", direction=ChecklistTemplate.Direction.ONBOARDING, actor=self.hr_admin)
        ChecklistTemplateItem.objects.create(template=draft, label="One task")

        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.post(f"/api/v1/checklist-templates/{draft.id}/publish/")
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/checklist-templates/{draft.id}/publish/")
        self.assertEqual(response.status_code, 200)


class InstanceVisibilityTests(ChecklistAPITestCase):
    def test_hr_admin_and_auditor_see_every_instance(self):
        for actor in (self.hr_admin, self.auditor):
            self.client.force_authenticate(user=actor.user)
            response = self.client.get("/api/v1/checklist-instances/")
            self.assertEqual(response.status_code, 200)
            ids = [row["id"] for row in response.data["results"]] if "results" in response.data else [
                row["id"] for row in response.data
            ]
            self.assertIn(self.instance.id, ids)

    def test_the_reports_own_manager_sees_it_the_outsider_manager_does_not(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.get("/api/v1/checklist-instances/")
        ids = [row["id"] for row in (response.data["results"] if "results" in response.data else response.data)]
        self.assertIn(self.instance.id, ids)

        self.client.force_authenticate(user=self.outsider_manager.user)
        response = self.client.get("/api/v1/checklist-instances/")
        ids = [row["id"] for row in (response.data["results"] if "results" in response.data else response.data)]
        self.assertNotIn(self.instance.id, ids)

    def test_the_employee_sees_their_own_instance_but_not_someone_elses(self):
        self.client.force_authenticate(user=self.report.user)
        response = self.client.get("/api/v1/checklist-instances/")
        ids = [row["id"] for row in (response.data["results"] if "results" in response.data else response.data)]
        self.assertIn(self.instance.id, ids)

        self.client.force_authenticate(user=self.outsider_report.user)
        response = self.client.get("/api/v1/checklist-instances/")
        ids = [row["id"] for row in (response.data["results"] if "results" in response.data else response.data)]
        self.assertNotIn(self.instance.id, ids)

    def test_manual_create_is_hr_admin_only(self):
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post("/api/v1/checklist-instances/", {
            "employee": self.outsider_report.id, "direction": "onboarding",
        })
        self.assertEqual(response.status_code, 403)


class TaskCompletionAccessTests(ChecklistAPITestCase):
    def _item(self, owner_role):
        return self.instance.items.get(owner_role=owner_role)

    def test_hr_admin_can_complete_any_task(self):
        item = self._item(ChecklistTemplateItem.OwnerRole.IT)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/checklist-items/{item.id}/complete/")
        self.assertEqual(response.status_code, 200)

    def test_line_manager_can_complete_a_line_manager_owned_task_for_their_own_report(self):
        item = self._item(ChecklistTemplateItem.OwnerRole.LINE_MANAGER)
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(f"/api/v1/checklist-items/{item.id}/complete/")
        self.assertEqual(response.status_code, 200)

    def test_line_manager_cannot_complete_an_it_owned_task_even_for_their_own_report(self):
        item = self._item(ChecklistTemplateItem.OwnerRole.IT)
        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(f"/api/v1/checklist-items/{item.id}/complete/")
        self.assertEqual(response.status_code, 403)

    def test_an_outsider_manager_cannot_complete_a_task_for_someone_outside_their_chain(self):
        item = self._item(ChecklistTemplateItem.OwnerRole.LINE_MANAGER)
        self.client.force_authenticate(user=self.outsider_manager.user)
        response = self.client.post(f"/api/v1/checklist-items/{item.id}/complete/")
        self.assertEqual(response.status_code, 404)  # outside their visible queryset entirely

    def test_the_employee_cannot_complete_their_own_task(self):
        item = self._item(ChecklistTemplateItem.OwnerRole.HR)
        self.client.force_authenticate(user=self.report.user)
        response = self.client.post(f"/api/v1/checklist-items/{item.id}/complete/")
        self.assertEqual(response.status_code, 403)

    def test_the_employee_can_still_read_their_own_checklist_items(self):
        self.client.force_authenticate(user=self.report.user)
        response = self.client.get(f"/api/v1/checklist-items/?instance={self.instance.id}")
        self.assertEqual(response.status_code, 200)

    def test_auditor_can_read_but_not_complete(self):
        item = self._item(ChecklistTemplateItem.OwnerRole.HR)
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get(f"/api/v1/checklist-items/?instance={self.instance.id}")
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f"/api/v1/checklist-items/{item.id}/complete/")
        self.assertEqual(response.status_code, 403)

    def test_reopen_follows_the_same_gate(self):
        item = self._item(ChecklistTemplateItem.OwnerRole.HR)
        complete_item(item, actor=self.hr_admin)

        self.client.force_authenticate(user=self.manager.user)
        response = self.client.post(f"/api/v1/checklist-items/{item.id}/reopen/")
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/checklist-items/{item.id}/reopen/")
        self.assertEqual(response.status_code, 200)
