"""C6: consultation-forum records, plan measures, progress snapshots
(design spec 2026-08-26). Service-level behaviour plus the access matrix
(spec §5) — including the forum-member carve-out and the POPIA redaction
of `representation` for non-EE readers."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from core_hr.data_quality import run_data_quality_checks
from core_hr.models import DataQualityException, Department, Employee, EmployeeVersion, JobGrade, Location, OccupationalLevel
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rbac_audit.models import AuditLogEntry, Role, RoleAssignment
from rest_framework.test import APIClient

from .constants import BARRIER_CATEGORIES
from .models import EEForumMeeting, EEForumMember, EEPlan, EEPlanMeasure, EEPlanProgressSnapshot, EEQuestionnaire, EEReport
from .services import forum_composition, take_progress_snapshot
from .validation import validate_report_data

User = get_user_model()

PLAN_START, PLAN_END = date(2025, 9, 1), date(2030, 8, 31)


class ForumPlanTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dept = Department.objects.create(name="Engineering", code="ENG")
        self.top = OccupationalLevel.objects.get(code="TOP")
        self.skilled = OccupationalLevel.objects.get(code="SKILLED")
        self.grade_top = JobGrade.objects.create(name="G1", code="G1", occupational_level=self.top)
        self.grade_skilled = JobGrade.objects.create(name="G5", code="G5", occupational_level=self.skilled)
        self.location = Location.objects.create(name="HO", code="HO", province=Location.Province.GAUTENG)
        self.plan = EEPlan.objects.create(
            plan_period_start=PLAN_START, plan_period_end=PLAN_END,
            annual_targets={"TOP": {"african_male": 50, "white_male": 10}},
            sector_targets={"TOP": {"male": 25.4, "female": 31.2, "total": 56.6}},
            eap_profile={"TOP": {"white_male": 5}},
            disability_5yr_target_pct=Decimal("3.0"),
        )

    def _hire(self, number, *, level=None, grade=None, race="african", gender="male", disability="no", role=None, username=None):
        user = User.objects.create_user(username=username or number.lower(), password="x") if (username or role) else None
        emp = Employee.objects.hire(
            employee_number=number, first_name=number, last_name="Test", date_of_birth=date(1985, 1, 1),
            work_email=f"{number.lower()}@example.com", hire_date=date(2020, 1, 1), department=self.dept,
            occupational_level=level or self.top, job_grade=grade or self.grade_top, location=self.location,
            race=race, gender=gender, disability_status=disability,
            citizenship_status=EmployeeVersion.CitizenshipStatus.SA_CITIZEN_BIRTH_DESCENT, user=user,
        )
        if role:
            RoleAssignment.objects.create(employee=emp, role=Role.objects.get(name=role))
        return emp

    def _auth(self, employee):
        self.client.force_authenticate(user=employee.user)


class CompositionTests(ForumPlanTestCase):
    def test_uncovered_levels_and_group_flags_are_derived_from_current_versions(self):
        black_top = self._hire("A1")
        white_male_skilled = self._hire("W1", level=self.skilled, grade=self.grade_skilled, race="white")
        self._hire("W2", level=self.skilled, grade=self.grade_skilled, race="white", gender="female")
        EEForumMember.objects.create(employee=black_top, representation="employee_nominated", role="chair", term_start=date(2026, 1, 1))
        result = forum_composition(as_of=date(2026, 6, 1))
        self.assertEqual(result["levels_uncovered"], ["SKILLED"])
        self.assertTrue(result["designated_groups_represented"])
        self.assertFalse(result["non_designated_represented"])
        self.assertFalse(result["union_nominated_present"])
        self.assertFalse(result["adequate"])

        EEForumMember.objects.create(employee=white_male_skilled, representation="union_nominated", term_start=date(2026, 1, 1))
        result = forum_composition(as_of=date(2026, 6, 1))
        self.assertEqual(result["levels_uncovered"], [])
        self.assertTrue(result["non_designated_represented"])
        self.assertTrue(result["union_nominated_present"])
        self.assertTrue(result["adequate"])
        # Booleans and codes only -- never a per-demographic count of the forum.
        self.assertNotIn("by_race", result)

    def test_expired_term_is_not_active(self):
        emp = self._hire("A1")
        EEForumMember.objects.create(employee=emp, representation="employee_nominated", term_start=date(2024, 1, 1), term_end=date(2024, 12, 31))
        self.assertEqual(forum_composition(as_of=date(2026, 6, 1))["active_member_count"], 0)


class SnapshotTests(ForumPlanTestCase):
    def test_snapshot_freezes_matrices_and_flags_both_directions(self):
        self._hire("A1")  # african male TOP -> 50% (meets 50 target)
        self._hire("W1", race="white")  # white male TOP -> 50%: over EAP (5), also above annual target (10)
        snap = take_progress_snapshot(self.plan, as_of=date(2026, 6, 1), note="Q2")
        self.assertEqual(snap.workforce_profile["TOP"]["african_male"], 1)
        self.assertEqual(snap.annual_target_gap_pct["TOP"]["african_male"], 0.0)
        self.assertEqual(snap.eap_gap_pct["TOP"]["white_male"], 45.0)
        self.assertEqual(snap.designated_group_pct["TOP"], {"male": 50.0, "female": 0.0, "total": 50.0})
        self.assertEqual(snap.sector_target_gap_pct["TOP"]["total"], round(50.0 - 56.6, 1))
        bases = {(f["row"], f["col"], f["basis"]) for f in snap.flags}
        self.assertIn(("TOP", "white_male", "over_eap"), bases)
        self.assertIn(("grand_total", "disability", "disability_target_shortfall"), bases)
        self.assertNotIn(("TOP", "african_male", "annual_target_shortfall"), bases)
        self.assertEqual(snap.disability_pct, Decimal("0.00"))

    def test_shortfall_is_flagged(self):
        self._hire("W1", race="white")
        snap = take_progress_snapshot(self.plan, as_of=date(2026, 6, 1))
        self.assertIn(("TOP", "african_male", "annual_target_shortfall"), {(f["row"], f["col"], f["basis"]) for f in snap.flags})

    def test_duplicate_day_and_out_of_period_rejected(self):
        take_progress_snapshot(self.plan, as_of=date(2026, 6, 1))
        with self.assertRaises(ValueError):
            take_progress_snapshot(self.plan, as_of=date(2026, 6, 1))
        with self.assertRaises(ValueError):
            take_progress_snapshot(self.plan, as_of=date(2031, 1, 1))


class ValidationEvidenceTests(ForumPlanTestCase):
    def _report(self, *, consultation, barriers=None, reasons=None):
        grid = {key: {"barriers": False, "aa_measures": False} for key, _ in BARRIER_CATEGORIES}
        grid.update(barriers or {})
        data = {
            "employer": {}, "questionnaire": {"barriers": grid, "consultation": consultation, "justifiable_reasons": reasons or {}},
            "workforce_profile": _matrix(), "disability_workforce": _matrix(), "recruitment": _matrix(),
            "promotion": _matrix(), "termination": _matrix(), "skills_development": _matrix(),
        }
        return EEReport.objects.create(
            form_type=EEReport.FormType.EEA2, report_year=2026, version=1,
            period_start=date(2025, 9, 1), period_end=date(2026, 8, 31), data=data,
        )

    def test_forum_claimed_without_meeting_is_flagged_and_converse(self):
        report = self._report(consultation={"consultative_body_or_ee_forum": True})
        self.assertTrue(any("no forum meeting is on record for 2026" in i for i in validate_report_data(report)))
        EEForumMeeting.objects.create(meeting_date=date(2026, 3, 1), title="Q1", report_year=2026)
        self.assertFalse(any("forum" in i.lower() for i in validate_report_data(report)))
        report.data["questionnaire"]["consultation"] = {"consultative_body_or_ee_forum": False}
        report.save()
        self.assertTrue(any("was not consulted, but 1 forum meeting" in i for i in validate_report_data(report)))

    def test_measures_claimed_without_plan_measure_is_flagged_and_converse(self):
        owner = self._hire("A1")
        report = self._report(consultation={}, barriers={"recruitment": {"barriers": True, "aa_measures": True}})
        issues = validate_report_data(report)
        self.assertTrue(any("'Recruitment' claims affirmative-action measures" in i for i in issues))
        EEPlanMeasure.objects.create(
            plan=self.plan, category="recruitment", measure_description="Targeted adverts", owner=owner,
            target_start=date(2026, 1, 1), target_end=date(2026, 12, 31),
        )
        EEPlanMeasure.objects.create(
            plan=self.plan, category="promotions", measure_description="Acting appointments", owner=owner,
            target_start=date(2026, 1, 1), target_end=date(2026, 12, 31),
        )
        issues = validate_report_data(report)
        self.assertFalse(any("'Recruitment'" in i for i in issues))
        self.assertTrue(any("'Promotions' answers No" in i for i in issues))

    def test_shortfall_without_justifiable_reason_is_flagged(self):
        # _matrix(): 1 white male in TOP -> african_male 0% vs 50% target.
        report = self._report(consultation={})
        self.assertTrue(any("TOP is below its annual target for african_male" in i for i in validate_report_data(report)))
        report.data["questionnaire"]["justifiable_reasons"] = {"TOP": ["insufficient_target_individuals"]}
        report.save()
        self.assertFalse(any("below its annual target" in i for i in validate_report_data(report)))


def _rows(data):
    """List responses are paginated only when the pagination class applies
    (a dict with `results`) -- accept either shape."""
    return data["results"] if isinstance(data, dict) else data


def _matrix():
    from . import aggregation

    m = aggregation.empty_matrix()
    m["TOP"]["white_male"] = 1
    m["total_permanent"]["white_male"] = 1
    m["grand_total"]["white_male"] = 1
    return m


class DataQualityTests(ForumPlanTestCase):
    def test_overdue_measure_opens_exception_for_owner_and_resolves_when_completed(self):
        owner = self._hire("A1")
        measure = EEPlanMeasure.objects.create(
            plan=self.plan, category="recruitment", measure_description="x", owner=owner,
            target_start=date(2025, 10, 1), target_end=date(2025, 12, 31), status="in_progress",
        )
        run_data_quality_checks()
        self.assertTrue(DataQualityException.objects.filter(
            employee=owner, exception_type=DataQualityException.ExceptionType.EE_MEASURE_OVERDUE, resolved_at__isnull=True,
        ).exists())
        measure.status = "completed"
        measure.save()
        run_data_quality_checks()
        self.assertFalse(DataQualityException.objects.filter(
            employee=owner, exception_type=DataQualityException.ExceptionType.EE_MEASURE_OVERDUE, resolved_at__isnull=True,
        ).exists())


@override_settings(MEDIA_ROOT=__import__("tempfile").mkdtemp())
class ForumApiTests(ForumPlanTestCase):
    def setUp(self):
        super().setUp()
        self.hr_admin = self._hire("HR1", role="hr_admin")
        self.ee_manager = self._hire("EE1", role="ee_manager")
        self.accounting_officer = self._hire("AO1", role="accounting_officer")
        self.auditor = self._hire("AUD1", role="auditor")
        self.member_emp = self._hire("M1", username="member", race="white", gender="female")
        self.outsider = self._hire("O1", username="outsider")
        self.member = EEForumMember.objects.create(
            employee=self.member_emp, representation="union_nominated", term_start=date(2026, 1, 1), notes="NUM",
        )
        self.attended = EEForumMeeting.objects.create(meeting_date=date(2026, 3, 1), title="Q1", report_year=2026)
        self.attended.attendees.add(self.member)
        self.not_attended = EEForumMeeting.objects.create(meeting_date=date(2026, 6, 1), title="Q2", report_year=2026)

    def test_ee_manager_can_add_member_and_meeting_with_pdf_minutes(self):
        self._auth(self.ee_manager)
        r = self.client.post("/api/v1/ee-forum-members/", {
            "employee": self.outsider.id, "representation": "employee_nominated", "role": "member", "term_start": "2026-02-01",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        r = self.client.post("/api/v1/ee-forum-meetings/", {
            "meeting_date": "2026-09-01", "title": "Q3", "report_year": 2026, "attendees": [self.member.id],
            "minutes_file": SimpleUploadedFile("minutes.pdf", b"%PDF-1.7\nminutes", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["minutes_content_type"], "application/pdf")
        self.assertTrue(r.data["has_minutes"])
        self.assertEqual(r.data["attendee_count"], 1)
        r = self.client.get(r.data["minutes_download_url"])
        self.assertEqual(r.status_code, 200)
        self.assertTrue(AuditLogEntry.objects.filter(entity_type="ee_reporting.EEForumMeeting", action=AuditLogEntry.Action.EXPORT).exists())

    def test_mislabelled_minutes_rejected(self):
        self._auth(self.hr_admin)
        r = self.client.post("/api/v1/ee-forum-meetings/", {
            "meeting_date": "2026-09-01", "title": "Q3", "report_year": 2026,
            "minutes_file": SimpleUploadedFile("minutes.pdf", b"not a pdf", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("minutes_file", r.data)

    def test_overlapping_term_rejected(self):
        self._auth(self.ee_manager)
        r = self.client.post("/api/v1/ee-forum-members/", {
            "employee": self.member_emp.id, "representation": "employee_nominated", "term_start": "2026-06-01",
        }, format="json")
        self.assertEqual(r.status_code, 400)

    def test_accounting_officer_and_auditor_read_only(self):
        for actor in (self.accounting_officer, self.auditor):
            self._auth(actor)
            self.assertEqual(len(_rows(self.client.get("/api/v1/ee-forum-members/").data)), 1)
            self.assertEqual(len(_rows(self.client.get("/api/v1/ee-forum-meetings/").data)), 2)
            self.assertEqual(self.client.get("/api/v1/ee-forum-members/composition/").status_code, 200)
            r = self.client.post("/api/v1/ee-forum-meetings/", {"meeting_date": "2026-09-01", "title": "x", "report_year": 2026}, format="json")
            self.assertEqual(r.status_code, 403)

    def test_member_sees_roster_and_own_meetings_only_with_representation_redacted(self):
        self._auth(self.member_emp)
        rows = _rows(self.client.get("/api/v1/ee-forum-members/").data)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("representation", rows[0])
        self.assertNotIn("notes", rows[0])
        rows = _rows(self.client.get("/api/v1/ee-forum-meetings/").data)
        self.assertEqual([m["id"] for m in rows], [self.attended.id])
        self.assertEqual(self.client.get(f"/api/v1/ee-forum-meetings/{self.not_attended.id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/ee-forum-members/composition/").status_code, 403)
        r = self.client.post("/api/v1/ee-forum-meetings/", {"meeting_date": "2026-09-01", "title": "x", "report_year": 2026}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_ee_roles_see_representation(self):
        self._auth(self.ee_manager)
        self.assertEqual(_rows(self.client.get("/api/v1/ee-forum-members/").data)[0]["representation"], "union_nominated")

    def test_non_member_employee_sees_nothing(self):
        self._auth(self.outsider)
        self.assertEqual(len(_rows(self.client.get("/api/v1/ee-forum-members/").data)), 0)
        self.assertEqual(len(_rows(self.client.get("/api/v1/ee-forum-meetings/").data)), 0)
        self.assertEqual(self.client.get(f"/api/v1/ee-forum-meetings/{self.attended.id}/download_minutes/").status_code, 404)


class PlanApiTests(ForumPlanTestCase):
    def setUp(self):
        super().setUp()
        self.hr_admin = self._hire("HR1", role="hr_admin")
        self.ee_manager = self._hire("EE1", role="ee_manager")
        self.accounting_officer = self._hire("AO1", role="accounting_officer")
        self.line_manager = self._hire("LM1", role="line_manager")
        self.plain = self._hire("P1", username="plain")

    def _measure_payload(self, **overrides):
        payload = {
            "plan": self.plan.id, "category": "recruitment", "barrier_description": "Few designated applicants",
            "measure_description": "Advertise in community media", "owner": self.ee_manager.id,
            "target_start": "2026-01-01", "target_end": "2026-12-31",
        }
        payload.update(overrides)
        return payload

    def test_ee_manager_creates_measure_owner_and_dates_required_and_inside_plan(self):
        self._auth(self.ee_manager)
        r = self.client.post("/api/v1/ee-plan-measures/", self._measure_payload(), format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["category_label"], "Recruitment")
        r = self.client.post("/api/v1/ee-plan-measures/", {k: v for k, v in self._measure_payload().items() if k != "owner"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/v1/ee-plan-measures/", self._measure_payload(target_end="2031-01-01"), format="json")
        self.assertEqual(r.status_code, 400)

    def test_accounting_officer_reads_but_cannot_write_measures(self):
        self._auth(self.accounting_officer)
        self.assertEqual(self.client.get("/api/v1/ee-plan-measures/").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/ee-plan-measures/", self._measure_payload(), format="json").status_code, 403)

    def test_line_manager_and_plain_employee_get_403(self):
        for actor in (self.line_manager, self.plain):
            self._auth(actor)
            self.assertEqual(self.client.get("/api/v1/ee-plan-measures/").status_code, 403)
            self.assertEqual(self.client.get("/api/v1/ee-plan-snapshots/").status_code, 403)

    def test_take_snapshot_suppresses_for_accounting_officer_but_not_hr_admin(self):
        self._hire("X1", race="indian", gender="female")
        self._auth(self.ee_manager)
        r = self.client.post("/api/v1/ee-plan-snapshots/take/", {"plan": self.plan.id, "as_of": "2026-06-01", "note": "Q2"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        snapshot_id = r.data["id"]
        self.assertEqual(self.client.post("/api/v1/ee-plan-snapshots/take/", {"plan": self.plan.id, "as_of": "2026-06-01"}, format="json").status_code, 400)

        self._auth(self.hr_admin)
        r = self.client.get(f"/api/v1/ee-plan-snapshots/{snapshot_id}/")
        self.assertFalse(r.data["small_cell_suppression_applied"])
        self.assertEqual(r.data["workforce_profile"]["TOP"]["indian_female"], 1)

        self._auth(self.accounting_officer)
        r = self.client.get(f"/api/v1/ee-plan-snapshots/{snapshot_id}/")
        self.assertTrue(r.data["small_cell_suppression_applied"])
        self.assertEqual(r.data["workforce_profile"]["TOP"]["indian_female"], "<5")
        r = self.client.get(f"/api/v1/ee-plan-snapshots/?plan={self.plan.id}")
        self.assertEqual(_rows(r.data)[0]["workforce_profile"]["TOP"]["indian_female"], "<5")
        # Raw stored value is unsuppressed.
        self.assertEqual(EEPlanProgressSnapshot.objects.get(pk=snapshot_id).workforce_profile["TOP"]["indian_female"], 1)

    def test_snapshots_are_create_only(self):
        snap = take_progress_snapshot(self.plan, as_of=date(2026, 6, 1))
        self._auth(self.hr_admin)
        self.assertEqual(self.client.delete(f"/api/v1/ee-plan-snapshots/{snap.id}/").status_code, 405)
        self.assertEqual(self.client.patch(f"/api/v1/ee-plan-snapshots/{snap.id}/", {"note": "x"}, format="json").status_code, 405)
        self.assertEqual(self.client.post("/api/v1/ee-plan-snapshots/", {"plan": self.plan.id}, format="json").status_code, 405)

    def test_questionnaire_still_saves_untouched(self):
        """The validate-don't-derive decision: the Y/N stays writable and is
        never overwritten by forum/plan state."""
        self._auth(self.hr_admin)
        r = self.client.post("/api/v1/ee-questionnaires/", {"report_year": 2026, "consultation": {"consultative_body_or_ee_forum": True}}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(EEQuestionnaire.objects.get(report_year=2026).consultation["consultative_body_or_ee_forum"])
