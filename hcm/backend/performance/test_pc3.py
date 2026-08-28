"""PC-3: period archive, rating-distribution dashboard, ImprovementPlan.

Reuses ReviewTestCase's fixture and helpers (employee/head/hr_admin, a
two-KPI template, `_agreed`/`_open_final`/`_rate_all`) from PC-2's test file.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from core_hr.models import EmployeeVersion
from rbac_audit.models import Role, RoleAssignment

from .models import ImprovementPlan, PerformanceAgreement, PerformancePeriod
from .services import AgreementWorkflowError, archive_period, sign_agreement
from .test_agreements import PASSWORD
from .test_reviews import ReviewTestCase


class ArchivePeriodTests(ReviewTestCase):
    def _final_signed(self, **kwargs):
        agreement = self._agreed(**kwargs)
        self._open_final(agreement)
        self._rate_all(agreement, 4)
        sign_agreement(agreement, actor=agreement.employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        agreement.refresh_from_db()
        return agreement

    def test_archive_moves_final_signed_agreements_and_reports_outstanding(self):
        finished = self._final_signed()
        straggler_employee = self._hire("E020", "Still", "Draft", "stilldraft2", manager=self.head)
        from .services import create_agreement

        create_agreement(period=self.period, employee=straggler_employee, template=self.template)

        result = archive_period(self.period, actor=self.hr_admin)
        self.assertEqual(result, {"archived": 1, "outstanding": 1})

        finished.refresh_from_db()
        self.assertEqual(finished.status, PerformanceAgreement.Status.ARCHIVED)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, PerformancePeriod.Status.ARCHIVED)

    def test_only_hr_admin_can_archive_via_the_api(self):
        self._final_signed()
        self._login(self.head)
        response = self.client.post(f"/api/v1/performance-periods/{self.period.id}/archive/")
        self.assertEqual(response.status_code, 403)

        self._login(self.hr_admin)
        response = self.client.post(f"/api/v1/performance-periods/{self.period.id}/archive/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["archived"], 1)

    def test_archived_agreement_is_still_readable_and_downloadable(self):
        agreement = self._final_signed()
        archive_period(self.period, actor=self.hr_admin)
        agreement.refresh_from_db()
        self._login(agreement.employee)
        response = self.client.get(f"/api/v1/performance-agreements/{agreement.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "archived")
        self.assertEqual(len(response.data["documents"]), 2)  # midyear never opened here, so just contracting+final...

    def test_auditor_can_pull_the_full_signature_trail_of_an_archived_agreement(self):
        agreement = self._final_signed()
        archive_period(self.period, actor=self.hr_admin)
        agreement.refresh_from_db()

        auditor = self._hire("AUD2", "Ivy", "Auditor", "ivyauditor2")
        RoleAssignment.objects.create(employee=auditor, role=Role.objects.get(name="auditor"))
        self._login(auditor)

        response = self.client.get(f"/api/v1/performance-agreements/{agreement.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["signatures"]), 4)  # employee+head x (contracting, final)
        for doc in response.data["documents"]:
            pdf = self.client.get(doc["download_url"])
            self.assertEqual(pdf.status_code, 200)
            self.assertEqual(b"".join(pdf.streaming_content)[:5], b"%PDF-")

        blocked = self.client.post(f"/api/v1/performance-periods/{self.period.id}/archive/")
        self.assertEqual(blocked.status_code, 403)


class RatingDistributionTests(ReviewTestCase):
    def _signed_with_rating(self, employee, rating):
        agreement = self._agreed(employee=employee, weights=[Decimal("0.5"), Decimal("0.5")])
        self._open_final(agreement)
        self._rate_all(agreement, rating)
        sign_agreement(agreement, actor=employee, role="employee", password=PASSWORD)
        sign_agreement(agreement, actor=self.head, role="head", password=PASSWORD)
        return agreement

    def test_hr_admin_sees_unsuppressed_counts(self):
        self._signed_with_rating(self.employee, 4)
        self._login(self.hr_admin)
        response = self.client.get(f"/api/v1/performance-periods/{self.period.id}/rating-distribution/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["small_cell_suppression_applied"])
        division = response.data["by_division"]["Research and Innovation"]
        self.assertEqual(division["4"], 2)  # two KPIs both rated 4

    def test_line_manager_sees_suppressed_small_cells(self):
        self._signed_with_rating(self.employee, 4)
        self._login(self.head)
        response = self.client.get(f"/api/v1/performance-periods/{self.period.id}/rating-distribution/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["small_cell_suppression_applied"])
        division = response.data["by_division"]["Research and Innovation"]
        self.assertEqual(division["4"], "<5")

    def test_hr_admin_sees_unsuppressed_demographic_breakdowns(self):
        """The Code on integrating EE into HR practice's performance
        section calls for appraisal distributions reviewed across
        designated groups -- this is that moderation-step lens, reusing
        the same suppression rule as by_division rather than a division x
        demographic matrix."""
        self._signed_with_rating(self.employee, 4)
        self._login(self.hr_admin)
        response = self.client.get(f"/api/v1/performance-periods/{self.period.id}/rating-distribution/")
        self.assertEqual(response.status_code, 200)
        # self.employee's race/gender/disability_status are all left at
        # their NOT_DISCLOSED default by the fixture.
        self.assertEqual(response.data["by_race"]["not_disclosed"]["4"], 2)
        self.assertEqual(response.data["by_gender"]["not_disclosed"]["4"], 2)
        self.assertEqual(response.data["by_disability_status"]["not_disclosed"]["4"], 2)

    def test_line_manager_sees_suppressed_demographic_cells(self):
        self._signed_with_rating(self.employee, 4)
        self._login(self.head)
        response = self.client.get(f"/api/v1/performance-periods/{self.period.id}/rating-distribution/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["by_race"]["not_disclosed"]["4"], "<5")
        self.assertEqual(response.data["by_gender"]["not_disclosed"]["4"], "<5")
        self.assertEqual(response.data["by_disability_status"]["not_disclosed"]["4"], "<5")

    def test_rating_unit_declares_kpi_element_not_final_score(self):
        self._signed_with_rating(self.employee, 4)
        self._login(self.hr_admin)
        response = self.client.get(f"/api/v1/performance-periods/{self.period.id}/rating-distribution/")
        self.assertEqual(response.data["rating_unit"], "kpi_element")

    def test_breakdown_uses_the_version_as_at_period_end_not_today(self):
        """A department transfer or demographic correction made AFTER the
        period closed must not retroactively move the rating into a
        different group -- the regulatory review's "historical employee
        versions" P1 finding."""
        self._signed_with_rating(self.employee, 4)
        version1 = self.employee.current_version
        version1.race = "african"
        version1.valid_to = date(2027, 6, 1)
        version1.save(update_fields=["race", "valid_to"])
        version2_fields = {
            f: getattr(version1, f) for f in [
                "department", "job_title", "occupational_level", "job_grade", "manager",
                "employment_status", "citizenship_status", "location", "position", "contract_end_date",
                "gender", "disability_status", "disability_detail", "race_source", "disability_source",
            ]
        }
        EmployeeVersion.objects.create(
            employee=self.employee, valid_from=date(2027, 6, 1), valid_to=None,
            race="coloured", **version2_fields,
        )
        self._login(self.hr_admin)
        response = self.client.get(f"/api/v1/performance-periods/{self.period.id}/rating-distribution/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("african", response.data["by_race"])
        self.assertNotIn("coloured", response.data["by_race"])


class ImprovementPlanTests(ReviewTestCase):
    def setUp(self):
        super().setUp()
        self.agreement = self._agreed(weights=[Decimal("0.5"), Decimal("0.5")])
        self._open_final(self.agreement)
        self._rate_all(self.agreement, 2)  # -> hr_attention on final sign
        sign_agreement(self.agreement, actor=self.employee, role="employee", password=PASSWORD)
        sign_agreement(self.agreement, actor=self.head, role="head", password=PASSWORD)
        self.agreement.refresh_from_db()
        self.assertTrue(self.agreement.hr_attention)

    def _payload(self, **overrides):
        payload = {
            "agreement": self.agreement.id, "owner": self.head.id,
            "reasons": "Missed revenue target two quarters running.",
            "actions": "Weekly pipeline review with the Head; shadow a senior AE for Q2.",
            "review_date": "2026-10-01",
        }
        payload.update(overrides)
        return payload

    def test_head_can_create_a_plan_when_hr_attention_is_set(self):
        self._login(self.head)
        response = self.client.post("/api/v1/improvement-plans/", self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["outcome"], "open")
        plan = ImprovementPlan.objects.get(pk=response.data["id"])
        self.assertEqual(plan.created_by, self.head)

    def test_cannot_create_a_plan_without_hr_attention(self):
        star_performer = self._hire("E030", "Star", "Performer", "starperformer", manager=self.head)
        clean = self._agreed(employee=star_performer, weights=[Decimal("0.5"), Decimal("0.5")])
        self._open_final(clean)
        self._rate_all(clean, 5)
        sign_agreement(clean, actor=star_performer, role="employee", password=PASSWORD)
        sign_agreement(clean, actor=self.head, role="head", password=PASSWORD)
        clean.refresh_from_db()
        self.assertFalse(clean.hr_attention)

        self._login(self.head)
        response = self.client.post("/api/v1/improvement-plans/", self._payload(agreement=clean.id), format="json")
        self.assertEqual(response.status_code, 400)

    def test_employee_cannot_create_a_plan_but_can_read_their_own(self):
        self._login(self.employee)
        blocked = self.client.post("/api/v1/improvement-plans/", self._payload(), format="json")
        self.assertEqual(blocked.status_code, 403)

        self._login(self.head)
        self.client.post("/api/v1/improvement-plans/", self._payload(), format="json")

        self._login(self.employee)
        listing = self.client.get(f"/api/v1/improvement-plans/?agreement={self.agreement.id}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data["results"]), 1)

    def test_hr_admin_can_update_outcome(self):
        self._login(self.head)
        created = self.client.post("/api/v1/improvement-plans/", self._payload(), format="json")

        self._login(self.hr_admin)
        updated = self.client.patch(
            f"/api/v1/improvement-plans/{created.data['id']}/",
            {"outcome": "resolved", "outcome_notes": "Back on target for two consecutive months."},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["outcome"], "resolved")
