"""H3: the Notification model, its API, and the six write-through consumers
(PC reminders, comp approval, review launch, policy publish, liveness flag,
EE sign-off)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from core_hr.models import Department, Employee, JobGrade, Location, OccupationalLevel
from config.operational_metrics import render_prometheus
from performance.test_reviews import ReviewTestCase
from rbac_audit.models import Role, RoleAssignment

from .models import Notification
from .services import employees_with_role, notify, notify_many

User = get_user_model()
PASSWORD = "correct-horse-battery"


class NotificationsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.dept = Department.objects.create(name="Research and Innovation", code="RI")
        self.level = OccupationalLevel.objects.get(code="TOP")
        self.grade = JobGrade.objects.create(name="Grade 1", code="G1", occupational_level=self.level)
        self.location = Location.objects.create(name="Head Office", code="HO", province=Location.Province.GAUTENG)
        self.employee = self._hire("E001", "Willem", "Klopper", "employee")
        RoleAssignment.objects.create(employee=self.employee, role=Role.objects.get(name="employee"))

    def _hire(self, number, first, last, username):
        return Employee.objects.hire(
            employee_number=number, first_name=first, last_name=last, date_of_birth=date(1990, 1, 1),
            work_email=f"{username}@sentech.example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=self.level, job_grade=self.grade, location=self.location,
            user=User.objects.create_user(username=username, password=PASSWORD),
        )

    def _login(self, employee):
        client = APIClient()
        client.force_authenticate(user=employee.user)
        return client


class ServiceTests(NotificationsTestCase):
    def test_notify_creates_a_row_and_sends_email(self):
        notification = notify(recipient=self.employee, kind="pc_reminder", title="Test", body="Body", link="/my-performance")
        self.assertEqual(Notification.objects.count(), 1)
        self.assertIsNotNone(notification.emailed_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Test", mail.outbox[0].subject)
        self.assertEqual(mail.outbox[0].to, [self.employee.work_email])
        self.assertIn('hcm_notification_email_total{outcome="success"} 1', render_prometheus())

    @patch("notifications.services.send_mail", side_effect=RuntimeError("SMTP unavailable"))
    def test_email_failure_is_counted_without_breaking_in_app_delivery(self, _send_mail):
        notification = notify(recipient=self.employee, kind="pc_reminder", title="Still in app")
        self.assertIsNone(notification.emailed_at)
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())
        metrics = render_prometheus()
        self.assertIn('hcm_notification_email_total{outcome="attempt"} 1', metrics)
        self.assertIn('hcm_notification_email_total{outcome="failure"} 1', metrics)

    def test_notify_without_email_flag_skips_sending(self):
        notify(recipient=self.employee, kind="pc_reminder", title="Silent", email=False)
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(Notification.objects.get().emailed_at)

    def test_notify_many_batches(self):
        other = self._hire("E002", "Other", "Person", "otherperson")
        notify_many([self.employee, other], kind="policy_publish", title="New policy")
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 2)

    def test_employees_with_role(self):
        hr_admin = self._hire("HR01", "HR", "Admin", "hradmin")
        RoleAssignment.objects.create(employee=hr_admin, role=Role.objects.get(name="hr_admin"))
        found = list(employees_with_role("hr_admin"))
        self.assertEqual(found, [hr_admin])


class ApiTests(NotificationsTestCase):
    def test_employee_sees_only_their_own_notifications(self):
        other = self._hire("E002", "Other", "Person", "otherperson")
        notify(recipient=self.employee, kind="pc_reminder", title="Mine", email=False)
        notify(recipient=other, kind="pc_reminder", title="Not mine", email=False)

        client = self._login(self.employee)
        response = client.get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Mine")

    def test_unread_count_and_mark_read(self):
        n1 = notify(recipient=self.employee, kind="pc_reminder", title="One", email=False)
        notify(recipient=self.employee, kind="pc_reminder", title="Two", email=False)
        client = self._login(self.employee)

        count = client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(count.data["count"], 2)

        marked = client.post(f"/api/v1/notifications/{n1.id}/mark-read/")
        self.assertEqual(marked.status_code, 200)
        self.assertIsNotNone(marked.data["read_at"])

        count = client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(count.data["count"], 1)

    def test_mark_all_read(self):
        notify(recipient=self.employee, kind="pc_reminder", title="One", email=False)
        notify(recipient=self.employee, kind="pc_reminder", title="Two", email=False)
        client = self._login(self.employee)
        response = client.post("/api/v1/notifications/mark-all-read/")
        self.assertEqual(response.data["updated"], 2)
        self.assertEqual(client.get("/api/v1/notifications/unread-count/").data["count"], 0)

    def test_cannot_mark_someone_elses_notification_read(self):
        other = self._hire("E002", "Other", "Person", "otherperson")
        theirs = notify(recipient=other, kind="pc_reminder", title="Not yours", email=False)
        client = self._login(self.employee)
        response = client.post(f"/api/v1/notifications/{theirs.id}/mark-read/")
        self.assertEqual(response.status_code, 404)


class ConsumerWiringTests(NotificationsTestCase):
    """One smoke test per consumer -- the workflow's own test suite covers
    the business logic; this only proves the notify() call actually fires."""

    def test_comp_approval_notifies_the_proposer(self):
        from compensation.models import PayBand
        from compensation.services import approve_proposal, propose_compensation_change

        approver = self._hire("HR01", "HR", "Admin", "hradmin")
        proposer = self._hire("MGR1", "Manager", "One", "managerone")
        PayBand.objects.create(
            job_grade=self.grade, min_salary=Decimal("100000"), mid_salary=Decimal("500000"),
            max_salary=Decimal("900000"), valid_from=date(2020, 1, 1),
        )
        proposal = propose_compensation_change(
            employee=self.employee, proposed_annual_salary=Decimal("500000"), proposed_by=proposer,
        )
        approve_proposal(proposal, approver=approver)
        self.assertTrue(Notification.objects.filter(recipient=proposer, kind="comp_approval").exists())

    def test_policy_publish_notifies_every_current_employee(self):
        from policies.models import Policy
        from policies.services import publish_policy, record_policy_approval

        other = self._hire("E002", "Other", "Person", "otherperson")
        committee_member = self._hire("E003", "Committee", "Member", "committeemember")
        RoleAssignment.objects.create(
            employee=committee_member, role=Role.objects.get(name="policy_committee_member")
        )
        policy = Policy.objects.create(code="leave", title="Leave Policy", version=1, status=Policy.Status.DRAFT)
        record_policy_approval(policy, approver=committee_member)
        publish_policy(policy)
        self.assertTrue(Notification.objects.filter(recipient=self.employee, kind="policy_publish").exists())
        self.assertTrue(Notification.objects.filter(recipient=other, kind="policy_publish").exists())

    def test_liveness_flag_notifies_hr_admin(self):
        from identity_verification.services import enroll_employee, run_liveness_check
        from rbac_audit.consent import record_consent
        from rbac_audit.models import ConsentRecord

        hr_admin = self._hire("HR01", "HR", "Admin", "hradmin")
        RoleAssignment.objects.create(employee=hr_admin, role=Role.objects.get(name="hr_admin"))
        record_consent(
            employee=self.employee, purpose=ConsentRecord.Purpose.BIOMETRIC,
            lawful_basis=ConsentRecord.LawfulBasis.CONSENT, text_version="v1",
        )
        enroll_employee(employee=self.employee, descriptor=[0.1] * 128)
        run_liveness_check(employee=self.employee, descriptor=None)  # NO_FACE_DETECTED -> PENDING review
        self.assertTrue(Notification.objects.filter(recipient=hr_admin, kind="liveness_flag").exists())


class PerformanceConsumerWiringTests(ReviewTestCase):
    """review_launch and ee_signoff reuse PC-1/PC-2's rich agreement fixture
    (period/template/employee/head already wired) rather than rebuilding an
    equivalent one here."""

    def test_opening_midyear_notifies_every_affected_employee(self):
        agreement = self._agreed()
        self._open_midyear(agreement)
        self.assertTrue(
            Notification.objects.filter(recipient=agreement.employee, kind="review_launch").exists()
        )

    def test_employee_signing_notifies_the_head_and_head_signing_notifies_the_employee(self):
        from performance.services import sign_agreement
        from performance.test_agreements import PASSWORD

        agreement = self._agreed()
        self._open_midyear(agreement)
        sign_agreement(agreement, actor=self.employee, role="employee", password=PASSWORD)
        self.assertTrue(Notification.objects.filter(recipient=self.head, kind="ee_signoff").exists())

        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        self.assertTrue(
            Notification.objects.filter(recipient=self.employee, kind="ee_signoff", title__icontains="fully signed").exists()
        )
