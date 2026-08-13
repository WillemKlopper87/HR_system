from __future__ import annotations

from datetime import date

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.test import TestCase
from rbac_audit.models import Role, RoleAssignment
from rest_framework.test import APIClient

from .models import EEQuestionnaire, EEReport, EmployerConfig, RemunerationRecord
from .services import ee_manager_approve, generate_report, submit_for_review

User = get_user_model()


def _seed_reference_data():
    dept = Department.objects.create(name="Engineering", code="ENG")
    level = OccupationalLevel.objects.get(code="TOP")
    grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=level)
    location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
    return dept, level, grade, location


class EEReportingApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept, self.level, self.grade, self.location = _seed_reference_data()

        def _hire(number, username, role_name):
            emp = Employee.objects.hire(
                employee_number=number, first_name=username.title(), last_name="Test", date_of_birth=date(1985, 1, 1),
                work_email=f"{username}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
                occupational_level=self.level, job_grade=self.grade, location=self.location,
                race="african", gender="male",
                user=User.objects.create_user(username=username, password="x"),
            )
            RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name=role_name))
            return emp

        self.hr_admin = _hire("HR1", "hradmin", "hr_admin")
        self.ee_manager = _hire("EE1", "eemanager", "ee_manager")
        self.accounting_officer = _hire("AO1", "accountingofficer", "accounting_officer")
        self.auditor = _hire("AUD1", "auditor", "auditor")
        self.line_manager = _hire("MGR1", "manager", "line_manager")
        self.plain_employee = Employee.objects.hire(
            employee_number="E100", first_name="Plain", last_name="Employee", date_of_birth=date(1990, 1, 1),
            work_email="plain@example.com", hire_date=date(2021, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username="plain", password="x"),
        )

        self.period_start, self.period_end = date(2025, 9, 1), date(2026, 8, 31)

    def _setup_readiness(self):
        EmployerConfig.objects.create(
            trade_name="X", dti_registration_number="1", paye_sars_number="1", uif_reference_number="1",
            ee_reference_number="1", ceo_name="CEO", ee_senior_manager_name="EE", business_type="state_owned_enterprise",
        )
        EEQuestionnaire.objects.create(report_year=2026)


class ModuleWidePermissionTests(EEReportingApiTestCase):
    def test_line_manager_cannot_read(self):
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get("/api/v1/ee-reports/")
        self.assertEqual(response.status_code, 403)

    def test_plain_employee_cannot_read(self):
        self.client.force_authenticate(user=self.plain_employee.user)
        response = self.client.get("/api/v1/employer-config/")
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_read_but_not_write(self):
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get("/api/v1/employer-config/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/v1/employer-config/", {"trade_name": "X"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_ee_manager_can_read_but_not_write_config(self):
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.get("/api/v1/employer-config/")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/v1/employer-config/", {"trade_name": "X"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_hr_admin_can_write_config(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/employer-config/",
            {"trade_name": "Sentech", "business_type": "state_owned_enterprise"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)


class GenerateReportApiTests(EEReportingApiTestCase):
    def test_generate_blocked_when_not_ready(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/ee-reports/generate/",
            {"form_type": "eea2", "report_year": 2026, "period_start": str(self.period_start), "period_end": str(self.period_end)},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("issues", response.data)

    def test_generate_succeeds_once_ready(self):
        self._setup_readiness()
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(
            "/api/v1/ee-reports/generate/",
            {"form_type": "eea2", "report_year": 2026, "period_start": str(self.period_start), "period_end": str(self.period_end)},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "draft")
        self.assertIn("workforce_profile", response.data["data"])

    def test_ee_manager_cannot_generate(self):
        self._setup_readiness()
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(
            "/api/v1/ee-reports/generate/",
            {"form_type": "eea2", "report_year": 2026, "period_start": str(self.period_start), "period_end": str(self.period_end)},
            format="json",
        )
        self.assertEqual(response.status_code, 403)


class ApprovalActionApiTests(EEReportingApiTestCase):
    def setUp(self):
        super().setUp()
        self._setup_readiness()
        self.report = generate_report(
            form_type="eea2", report_year=2026, period_start=self.period_start, period_end=self.period_end
        )

    def test_hr_admin_submits_for_review(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/ee-reports/{self.report.id}/submit_for_review/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "pending_ee_review")

    def test_hr_admin_cannot_perform_ee_review_step(self):
        submit_for_review(self.report)
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post(f"/api/v1/ee-reports/{self.report.id}/ee_review/")
        self.assertEqual(response.status_code, 403)

    def test_ee_manager_can_perform_ee_review_step(self):
        submit_for_review(self.report)
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(f"/api/v1/ee-reports/{self.report.id}/ee_review/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "pending_signoff")

    def test_ee_manager_cannot_sign_off(self):
        submit_for_review(self.report)
        ee_manager_approve(self.report, actor=self.ee_manager)
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post(f"/api/v1/ee-reports/{self.report.id}/sign_off/", {"place": "JHB"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_accounting_officer_can_sign_off(self):
        submit_for_review(self.report)
        ee_manager_approve(self.report, actor=self.ee_manager)
        self.client.force_authenticate(user=self.accounting_officer.user)
        response = self.client.post(f"/api/v1/ee-reports/{self.report.id}/sign_off/", {"place": "Johannesburg"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "signed_off")
        self.assertEqual(response.data["signed_off_place"], "Johannesburg")


class ExportApiTests(EEReportingApiTestCase):
    def setUp(self):
        super().setUp()
        self._setup_readiness()
        self.report = generate_report(
            form_type="eea2", report_year=2026, period_start=self.period_start, period_end=self.period_end
        )

    def test_csv_export(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/ee-reports/{self.report.id}/export/?export_format=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_pdf_export(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/ee-reports/{self.report.id}/export/?export_format=pdf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_auditor_can_export(self):
        self.client.force_authenticate(user=self.auditor.user)
        response = self.client.get(f"/api/v1/ee-reports/{self.report.id}/export/?export_format=xml")
        self.assertEqual(response.status_code, 200)

    def test_invalid_format_rejected(self):
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get(f"/api/v1/ee-reports/{self.report.id}/export/?export_format=docx")
        self.assertEqual(response.status_code, 400)


class RemunerationImportApiTests(EEReportingApiTestCase):
    def test_hr_admin_can_import_csv(self):
        emp = Employee.objects.hire(
            employee_number="RE1", first_name="Rem", last_name="Test", date_of_birth=date(1990, 1, 1),
            work_email="rem@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
        )
        csv_text = f"employee_number,period_start,period_end,fixed_remuneration,variable_remuneration\n{emp.employee_number},2025-09-01,2026-08-31,300000,50000"
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.post("/api/v1/remuneration-records/import_csv/", {"csv": csv_text}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created"], 1)
        self.assertTrue(RemunerationRecord.objects.filter(employee=emp).exists())

    def test_ee_manager_cannot_import_csv(self):
        self.client.force_authenticate(user=self.ee_manager.user)
        response = self.client.post("/api/v1/remuneration-records/import_csv/", {"csv": "x"}, format="json")
        self.assertEqual(response.status_code, 403)


class EquityDashboardApiTests(EEReportingApiTestCase):
    def test_hr_admin_sees_unsuppressed_matrix(self):
        Employee.objects.hire(
            employee_number="X1", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="x1@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            race="african", gender="male",
        )
        self.client.force_authenticate(user=self.hr_admin.user)
        response = self.client.get("/api/v1/dashboards/equity/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["small_cell_suppression_applied"])
        self.assertIn("workforce_profile", response.data)

    def test_line_manager_gets_suppressed_matrix(self):
        # indian_female is a demographic column none of setUp()'s role-
        # holder employees use, so this is genuinely a count of 1 (< 5).
        Employee.objects.hire(
            employee_number="X1", first_name="A", last_name="B", date_of_birth=date(1990, 1, 1),
            work_email="x1@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            race="indian", gender="female",
        )
        self.client.force_authenticate(user=self.line_manager.user)
        response = self.client.get("/api/v1/dashboards/equity/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["small_cell_suppression_applied"])
        self.assertEqual(response.data["workforce_profile"]["TOP"]["indian_female"], "<5")
