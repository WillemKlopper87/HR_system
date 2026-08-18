"""PC-1: performance agreements — state machine, signing order, delegation, API.

The rules under test are the user's own process (KPI-Contracting-Investigation.md
§2a and the 2026-08-18 answers): FY 1 Apr–31 Mar, weights sum to 1.00, five
target descriptors per KPI, employee signs first then the Head, a designated
delegate may sign for an absent Head, HR receives but never signs.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from rbac_audit.models import AuditLogEntry, Role, RoleAssignment

from .models import (
    AgreementSignature,
    AgreementTemplate,
    PerformanceAgreement,
    PerformancePeriod,
    PeriodPhase,
    SigningDelegation,
    TemplateElement,
    TemplateSection,
)
from .services import (
    AgreementWorkflowError,
    approve_agreement,
    clone_period,
    create_agreement,
    generate_agreements_for_period,
    publish_template,
    return_agreement,
    sign_agreement,
    submit_agreement,
)

User = get_user_model()
PASSWORD = "correct-horse-battery"

LEVELS = {"1": "Below Target", "2": "Partially meets", "3": "On Target", "4": "Stretch", "5": "Exceeded Stretch"}


class AgreementTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.dept = Department.objects.create(name="Research and Innovation", code="RI")
        self.level = OccupationalLevel.objects.get(code="TOP")
        self.grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=self.level)
        self.location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)

        self.head = self._hire("H001", "Head", "Ofdivision", "head")
        self.employee = self._hire("E001", "Willem", "Klopper", "employee", manager=self.head)
        self.other = self._hire("E002", "Someone", "Else", "other")
        self.delegate = self._hire("D001", "Acting", "Head", "delegate")
        self.hr_admin = self._hire("HR01", "HR", "Admin", "hradmin")
        RoleAssignment.objects.create(employee=self.hr_admin, role=Role.objects.get(name="hr_admin"))
        for emp in (self.head, self.employee, self.other, self.delegate):
            RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name="employee"))
        RoleAssignment.objects.create(employee=self.head, role=Role.objects.get(name="line_manager"))
        RoleAssignment.objects.create(employee=self.delegate, role=Role.objects.get(name="line_manager"))

        self.period = PerformancePeriod.objects.create(
            name="2026/27", start_date=date(2026, 4, 1), end_date=date(2027, 3, 31)
        )
        PeriodPhase.objects.create(
            period=self.period, stage=PeriodPhase.Stage.CONTRACTING,
            opens_on=date(2026, 4, 1), due_on=date(2026, 4, 30),
        )
        PeriodPhase.objects.create(
            period=self.period, stage=PeriodPhase.Stage.MIDYEAR, opens_on=date(2026, 9, 1), due_on=date(2026, 9, 30)
        )
        self.template = self._template()
        self.client = APIClient()

    def _hire(self, number, first, last, username, manager=None):
        return Employee.objects.hire(
            employee_number=number, first_name=first, last_name=last, date_of_birth=date(1990, 1, 1),
            work_email=f"{username}@sentech.example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location, manager=manager,
            user=User.objects.create_user(username=username, password=PASSWORD),
        )

    def _template(self, *, weights=(Decimal("0.4"), Decimal("0.6")), publish=True):
        template = AgreementTemplate.objects.create(name="Sentech Individual Scorecard", version=1, period=self.period)
        section = TemplateSection.objects.create(template=template, title="DRIVE SUSTAINABLE GROWTH", order=0)
        for i, weight in enumerate(weights):
            TemplateElement.objects.create(
                template=template, section=section, kpa_description="Financial Sustainability",
                kpi_title=f"Diversified revenue growth {i + 1}", metric="ZAR", default_weight=weight,
                level_descriptors=dict(LEVELS), order=i,
            )
        if publish:
            publish_template(template)
        return template

    def _agreement(self):
        return create_agreement(period=self.period, employee=self.employee, template=self.template)

    def _login(self, employee):
        self.client.force_authenticate(user=employee.user)
        return self.client


class PeriodAndTemplateTests(AgreementTestCase):
    def test_clone_period_rolls_the_financial_year_forward(self):
        nxt = clone_period(self.period, name="2027/28")
        self.assertEqual((nxt.start_date, nxt.end_date), (date(2027, 4, 1), date(2028, 3, 31)))
        self.assertEqual(
            sorted(nxt.phases.values_list("stage", "opens_on", "due_on")),
            sorted([
                ("contracting", date(2027, 4, 1), date(2027, 4, 30)),
                ("midyear", date(2027, 9, 1), date(2027, 9, 30)),
            ]),
        )
        # reminder offsets carry over with their default
        self.assertEqual(nxt.phase("contracting").reminder_offsets_days, [28, 14, 7, 1])

    def test_clone_refuses_a_duplicate_name(self):
        with self.assertRaises(AgreementWorkflowError):
            clone_period(self.period, name="2026/27")

    def test_template_must_total_100_percent_and_carry_all_five_descriptors(self):
        bad = AgreementTemplate.objects.create(name="Bad", version=1)
        section = TemplateSection.objects.create(template=bad, title="X", order=0)
        TemplateElement.objects.create(
            template=bad, section=section, kpi_title="Half a scorecard", default_weight=Decimal("0.5"),
            level_descriptors=dict(LEVELS),
        )
        with self.assertRaisesMessage(AgreementWorkflowError, "must sum to 1.00"):
            publish_template(bad)

        TemplateElement.objects.create(
            template=bad, section=section, kpi_title="No descriptors", default_weight=Decimal("0.5"),
            level_descriptors={"1": "only one"},
        )
        with self.assertRaisesMessage(AgreementWorkflowError, "missing target descriptors"):
            publish_template(bad)

    def test_template_targeting_selects_by_grade(self):
        other_grade = JobGrade.objects.create(name="Grade 9", code="G9", occupational_level=self.level)
        self.template.job_grades.set([other_grade])
        self.assertFalse(self.template.applies_to(self.employee))
        self.template.job_grades.set([self.grade])
        self.assertTrue(self.template.applies_to(self.employee))


class AgreementLifecycleTests(AgreementTestCase):
    def test_agreement_instantiates_the_template_and_snapshots_the_head(self):
        agreement = self._agreement()
        self.assertEqual(agreement.head, self.head)
        self.assertEqual(agreement.template_version, 1)
        self.assertEqual(agreement.elements.count(), 2)
        self.assertEqual(agreement.total_weight, Decimal("1.0000"))
        self.assertEqual(agreement.elements.first().level_descriptors["3"], "On Target")
        # a later reporting change does not move who signs
        self.employee.apply_lifecycle_event(
            event_type="transfer", effective_date=date(2026, 6, 1), manager=self.other
        )
        agreement.refresh_from_db()
        self.assertEqual(agreement.head, self.head)

    def test_one_agreement_per_employee_per_period(self):
        self._agreement()
        with self.assertRaisesMessage(AgreementWorkflowError, "already has an agreement"):
            self._agreement()

    def test_generate_for_period_is_idempotent(self):
        first = generate_agreements_for_period(self.period)
        self.assertEqual(first["created"], 5)
        second = generate_agreements_for_period(self.period)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["skipped"], 5)

    def test_submission_requires_weights_to_total_one(self):
        agreement = self._agreement()
        element = agreement.elements.first()
        element.weight = Decimal("0.1")
        element.save()
        with self.assertRaisesMessage(AgreementWorkflowError, "must sum to 1.00"):
            submit_agreement(agreement, actor=self.employee)

    def test_only_the_employee_submits_their_own_agreement(self):
        agreement = self._agreement()
        with self.assertRaisesMessage(AgreementWorkflowError, "Only the employee submits"):
            submit_agreement(agreement, actor=self.head)

    def test_return_requires_a_reason_and_reopens_for_editing(self):
        agreement = self._agreement()
        submit_agreement(agreement, actor=self.employee)
        with self.assertRaises(AgreementWorkflowError):
            return_agreement(agreement, actor=self.head, reason="   ")
        return_agreement(agreement, actor=self.head, reason="Targets for KPI 2 are too vague")
        self.assertEqual(agreement.status, PerformanceAgreement.Status.RETURNED)
        self.assertTrue(agreement.is_editable)
        submit_agreement(agreement, actor=self.employee)
        self.assertEqual(agreement.status, PerformanceAgreement.Status.SUBMITTED)
        self.assertEqual(agreement.return_reason, "")


class SigningTests(AgreementTestCase):
    def _approved(self):
        agreement = self._agreement()
        submit_agreement(agreement, actor=self.employee)
        approve_agreement(agreement, actor=self.head)
        return agreement

    def test_employee_signs_first_then_head(self):
        agreement = self._approved()
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        self.assertEqual(agreement.status, PerformanceAgreement.Status.EMPLOYEE_SIGNED)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        self.assertEqual(agreement.status, PerformanceAgreement.Status.AGREED)
        self.assertIsNotNone(agreement.agreed_at)
        self.assertEqual([s.role for s in agreement.signatures.all()], ["employee", "head"])

    def test_head_cannot_sign_before_the_employee(self):
        agreement = self._approved()
        with self.assertRaisesMessage(AgreementWorkflowError, "The employee signs first"):
            sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        self.assertEqual(agreement.signatures.count(), 0)

    def test_employee_cannot_sign_before_the_head_approves(self):
        agreement = self._agreement()
        submit_agreement(agreement, actor=self.employee)
        with self.assertRaisesMessage(AgreementWorkflowError, "approved by your Head"):
            sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)

    def test_wrong_password_does_not_record_a_signature(self):
        agreement = self._approved()
        with self.assertRaisesMessage(AgreementWorkflowError, "Password confirmation failed"):
            sign_agreement(agreement, actor=self.employee, role="employee", password="nope")
        self.assertEqual(agreement.signatures.count(), 0)
        self.assertEqual(agreement.documents.count(), 0)

    def test_signature_binds_the_exact_pdf_and_is_audit_logged(self):
        agreement = self._approved()
        signature = sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        document = agreement.documents.get()
        self.assertEqual(signature.document_sha256, document.sha256)
        self.assertEqual(len(signature.document_sha256), 64)
        self.assertTrue(document.pdf.name.endswith(".pdf"))
        document.pdf.open("rb")
        self.assertTrue(document.pdf.read(5).startswith(b"%PDF-"))
        document.pdf.close()
        self.assertTrue(
            AuditLogEntry.objects.filter(
                entity_type="performance.AgreementSignature", fields_touched__contains="employee signature"
            ).exists()
        )

    def test_a_third_party_cannot_sign_either_role(self):
        agreement = self._approved()
        with self.assertRaisesMessage(AgreementWorkflowError, "Only the employee can sign as the employee"):
            sign_agreement(agreement, actor=self.other, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        with self.assertRaisesMessage(AgreementWorkflowError, "Only the Head"):
            sign_agreement(agreement, actor=self.other, role="head", password=PASSWORD)

    def test_hr_admin_cannot_sign_for_anyone(self):
        agreement = self._approved()
        with self.assertRaises(AgreementWorkflowError):
            sign_agreement(agreement, actor=self.hr_admin, role="employee", password=PASSWORD)
        with self.assertRaises(AgreementWorkflowError):
            sign_agreement(agreement, actor=self.hr_admin, role="head", password=PASSWORD)

    def test_the_same_signature_cannot_be_recorded_twice(self):
        agreement = self._approved()
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        with self.assertRaisesMessage(AgreementWorkflowError, "already been recorded"):
            sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)

    def test_an_active_delegate_signs_for_the_head_and_is_recorded_as_acting(self):
        agreement = self._approved()
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        today = date.today()
        SigningDelegation.objects.create(
            delegator=self.head, delegate=self.delegate, start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7), reason="Head on leave",
        )
        signature = sign_agreement(agreement, actor=self.delegate, role="head", password=PASSWORD)
        self.assertEqual(signature.signer, self.delegate)
        self.assertEqual(signature.acting_for, self.head)
        self.assertEqual(agreement.status, PerformanceAgreement.Status.AGREED)

    def test_a_delegation_outside_its_window_or_revoked_does_not_authorise(self):
        agreement = self._approved()
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        today = date.today()
        expired = SigningDelegation.objects.create(
            delegator=self.head, delegate=self.delegate,
            start_date=today - timedelta(days=30), end_date=today - timedelta(days=1),
        )
        with self.assertRaisesMessage(AgreementWorkflowError, "Only the Head"):
            sign_agreement(agreement, actor=self.delegate, role="head", password=PASSWORD)
        expired.start_date, expired.end_date = today, today
        expired.save()
        expired.revoked_at = expired.created_at
        expired.save()
        with self.assertRaisesMessage(AgreementWorkflowError, "Only the Head"):
            sign_agreement(agreement, actor=self.delegate, role="head", password=PASSWORD)

    def test_amendment_bumps_the_revision_and_keeps_earlier_signatures(self):
        agreement = self._approved()
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        from .services import amend_agreement

        amend_agreement(agreement, actor=self.head, reason="5G target moved after the budget cut")
        self.assertEqual(agreement.revision, 2)
        self.assertEqual(agreement.status, PerformanceAgreement.Status.DRAFT)
        self.assertEqual(agreement.signatures.count(), 2)  # rev 1's signatures are history, not deleted
        submit_agreement(agreement, actor=self.employee)
        approve_agreement(agreement, actor=self.head)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        self.assertEqual(agreement.signatures.filter(revision=2).count(), 1)
        self.assertEqual(agreement.documents.count(), 2)  # one snapshot per revision


class AgreementApiTests(AgreementTestCase):
    def test_employee_sees_only_their_own_agreement_head_sees_the_team(self):
        mine = self._agreement()
        theirs = create_agreement(period=self.period, employee=self.other, template=self.template)

        self._login(self.employee)
        ids = [a["id"] for a in self.client.get("/api/v1/performance-agreements/").data["results"]]
        self.assertEqual(ids, [mine.id])
        self.assertEqual(self.client.get(f"/api/v1/performance-agreements/{theirs.id}/").status_code, 404)

        self._login(self.head)
        head_ids = {a["id"] for a in self.client.get("/api/v1/performance-agreements/").data["results"]}
        self.assertIn(mine.id, head_ids)

        self._login(self.hr_admin)
        admin_ids = {a["id"] for a in self.client.get("/api/v1/performance-agreements/").data["results"]}
        self.assertEqual(admin_ids, {mine.id, theirs.id})

    def test_full_contracting_flow_through_the_api(self):
        agreement = self._agreement()
        url = f"/api/v1/performance-agreements/{agreement.id}/"

        self._login(self.employee)
        self.assertEqual(self.client.post(url + "submit/").status_code, 200)
        # the employee may not approve their own scorecard
        self.assertEqual(self.client.post(url + "approve/").status_code, 403)

        self._login(self.head)
        returned = self.client.post(url + "return/", {"reason": "Add a stretch target to KPI 2"}, format="json")
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(returned.data["status"], "returned")

        self._login(self.employee)
        self.client.post(url + "submit/")
        self._login(self.head)
        self.assertEqual(self.client.post(url + "approve/").status_code, 200)

        # the Head cannot sign yet — 409, with a reason the UI can show
        early = self.client.post(url + "sign/", {"role": "head", "password": PASSWORD}, format="json")
        self.assertEqual(early.status_code, 409)
        self.assertIn("employee signs first", early.data["detail"].lower())
        self.assertFalse(self.client.get(url + "can-sign/").data["as_head"])

        self._login(self.employee)
        can = self.client.get(url + "can-sign/").data
        self.assertTrue(can["as_employee"])
        signed = self.client.post(url + "sign/", {"role": "employee", "password": PASSWORD}, format="json")
        self.assertEqual(signed.status_code, 200)
        self.assertEqual(signed.data["status"], "employee_signed")

        self._login(self.head)
        self.assertTrue(self.client.get(url + "can-sign/").data["as_head"])
        final = self.client.post(url + "sign/", {"role": "head", "password": PASSWORD}, format="json")
        self.assertEqual(final.status_code, 200)
        self.assertEqual(final.data["status"], "agreed")
        self.assertEqual(len(final.data["signatures"]), 2)

        # HR receives it: visible, downloadable, but no signing route
        self._login(self.hr_admin)
        detail = self.client.get(url).data
        self.assertEqual(detail["status"], "agreed")
        document_id = detail["documents"][0]["id"]
        download = self.client.get(url + f"documents/{document_id}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/pdf")
        refused = self.client.post(url + "sign/", {"role": "head", "password": PASSWORD}, format="json")
        self.assertEqual(refused.status_code, 400)

    def test_agreement_state_cannot_be_patched_directly(self):
        agreement = self._agreement()
        self._login(self.hr_admin)
        response = self.client.patch(
            f"/api/v1/performance-agreements/{agreement.id}/", {"status": "agreed"}, format="json"
        )
        self.assertEqual(response.status_code, 405)

    def test_element_weights_are_editable_only_while_the_agreement_is_open(self):
        agreement = self._agreement()
        element, other_element = list(agreement.elements.all())
        self._login(self.employee)
        ok = self.client.patch(f"/api/v1/agreement-elements/{element.id}/", {"weight": "0.45"}, format="json")
        self.assertEqual(ok.status_code, 200)
        # keep the scorecard at 100% so it can still be submitted
        self.client.patch(f"/api/v1/agreement-elements/{other_element.id}/", {"weight": "0.55"}, format="json")
        agreement.refresh_from_db()
        submit_agreement(agreement, actor=self.employee)
        approve_agreement(agreement, actor=self.head)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        blocked = self.client.patch(f"/api/v1/agreement-elements/{element.id}/", {"weight": "0.10"}, format="json")
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("amend", str(blocked.data).lower())

    def test_locked_elements_cannot_be_edited_even_in_draft(self):
        agreement = self._agreement()
        element = agreement.elements.first()
        element.locked = True
        element.save()
        self._login(self.employee)
        response = self.client.patch(f"/api/v1/agreement-elements/{element.id}/", {"weight": "0.9"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("cascaded", str(response.data).lower())

    def test_periods_are_readable_by_everyone_and_writable_only_by_hr_admin(self):
        self._login(self.employee)
        self.assertEqual(self.client.get("/api/v1/performance-periods/").status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/v1/performance-periods/",
                {"name": "2028/29", "start_date": "2028-04-01", "end_date": "2029-03-31"}, format="json",
            ).status_code, 403,
        )
        self._login(self.hr_admin)
        created = self.client.post(
            "/api/v1/performance-periods/",
            {"name": "2028/29", "start_date": "2028-04-01", "end_date": "2029-03-31"}, format="json",
        )
        self.assertEqual(created.status_code, 201)

    def test_completion_dashboard_counts_signed_agreements_by_division(self):
        agreement = self._agreement()
        create_agreement(period=self.period, employee=self.other, template=self.template)
        submit_agreement(agreement, actor=self.employee)
        approve_agreement(agreement, actor=self.head)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)

        self._login(self.hr_admin)
        data = self.client.get(f"/api/v1/performance-periods/{self.period.id}/completion/").data
        self.assertEqual((data["total"], data["signed"], data["outstanding"]), (2, 1, 1))
        self.assertEqual(data["completion_pct"], 50.0)
        self.assertEqual(data["by_division"][0]["division"], "Research and Innovation")

    def test_a_head_delegates_signing_only_for_themselves(self):
        self._login(self.head)
        today = date.today().isoformat()
        ok = self.client.post("/api/v1/signing-delegations/", {
            "delegator": self.head.id, "delegate": self.delegate.id, "start_date": today, "end_date": today,
            "reason": "Annual leave",
        }, format="json")
        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertTrue(ok.data["is_active"])

        bad = self.client.post("/api/v1/signing-delegations/", {
            "delegator": self.other.id, "delegate": self.delegate.id, "start_date": today, "end_date": today,
        }, format="json")
        self.assertEqual(bad.status_code, 403)

        self_deal = self.client.post("/api/v1/signing-delegations/", {
            "delegator": self.head.id, "delegate": self.head.id, "start_date": today, "end_date": today,
        }, format="json")
        self.assertEqual(self_deal.status_code, 400)
