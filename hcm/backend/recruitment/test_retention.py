from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from core_hr.models import Department, JobGrade, Location, OccupationalLevel
from rbac_audit import retention
from rbac_audit.models import RetentionRule

from .models import Applicant, ApplicantStageEvent, Requisition


def _rule(entity_type, **fields):
    """Defaults for these entity types are seeded by migration 0007 — override, don't collide."""
    rule, _ = RetentionRule.objects.update_or_create(entity_type=entity_type, defaults=fields)
    return rule


class ApplicantRetentionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Engineering", code="ENG")
        self.level = OccupationalLevel.objects.get(code="TOP")
        self.grade = JobGrade.objects.create(name="G1", code="G1", occupational_level=self.level)
        self.location = Location.objects.create(name="HO", code="HO", province=Location.Province.GAUTENG)
        self.req = Requisition.objects.create(
            title="Backend Engineer", department=self.dept, occupational_level=self.level, job_grade=self.grade,
            location=self.location, headcount=1, status=Requisition.Status.OPEN, opened_at=date(2025, 1, 1),
        )
        self.now = timezone.now()
        _rule("recruitment.Applicant", period_months=12, action=RetentionRule.Action.ANONYMISE
        )

    def _applicant(self, stage, months_since_update, **kw):
        a = Applicant.objects.create(
            requisition=self.req, first_name=kw.get("first", "Alex"), last_name=kw.get("last", "Applicant"),
            email=kw.get("email", "alex@example.com"), phone="0821234567", date_of_birth=date(1995, 3, 3),
            current_stage=stage, rejected_reason="Not a fit" if stage == Applicant.Stage.REJECTED else "",
        )
        ApplicantStageEvent.objects.create(applicant=a, to_stage=stage, notes="Interview notes mention family details")
        Applicant.objects.filter(pk=a.pk).update(updated_at=self.now - timedelta(days=31 * months_since_update))
        return a

    def test_handler_is_registered_by_app_config(self):
        self.assertIsNotNone(retention.get_handler("recruitment.Applicant"))

    def test_old_rejected_applicant_is_anonymised_others_untouched(self):
        old_rejected = self._applicant(Applicant.Stage.REJECTED, 14, email="old@example.com")
        recent_rejected = self._applicant(Applicant.Stage.REJECTED, 2, email="recent@example.com")
        old_hired = self._applicant(Applicant.Stage.HIRED, 14, email="hired@example.com")
        old_active = self._applicant(Applicant.Stage.INTERVIEW, 14, email="active@example.com")

        results = {r.entity_type: r for r in retention.run_retention(now=self.now)}
        self.assertEqual(results["recruitment.Applicant"].affected, 1)

        old_rejected.refresh_from_db()
        self.assertEqual(old_rejected.first_name, "Anonymised")
        self.assertEqual(old_rejected.last_name, f"Applicant {old_rejected.pk}")
        self.assertNotIn("old@", old_rejected.email)
        self.assertEqual(old_rejected.phone, "")
        self.assertEqual(old_rejected.date_of_birth, date(1900, 1, 1))
        self.assertIsNotNone(old_rejected.anonymised_at)
        self.assertEqual(old_rejected.current_stage, Applicant.Stage.REJECTED)  # pipeline outcome kept for stats
        # free-text that may carry PII is cleared; the audit trail of stage moves stays
        self.assertEqual(old_rejected.stage_events.count(), 1)
        self.assertEqual(old_rejected.stage_events.first().notes, "")
        # simple-history rows would otherwise still hold the original PII
        self.assertFalse(old_rejected.history.filter(first_name="Alex").exists())

        for a in (recent_rejected, old_hired, old_active):
            a.refresh_from_db()
            self.assertEqual(a.first_name, "Alex")
            self.assertIsNone(a.anonymised_at)

    def test_anonymise_is_idempotent(self):
        self._applicant(Applicant.Stage.REJECTED, 14)
        retention.run_retention(now=self.now)
        again = {r.entity_type: r for r in retention.run_retention(now=self.now)}
        self.assertEqual(again["recruitment.Applicant"].affected, 0)

    def test_dry_run_reports_without_changing(self):
        a = self._applicant(Applicant.Stage.REJECTED, 14)
        results = {r.entity_type: r for r in retention.run_retention(now=self.now, dry_run=True)}
        self.assertEqual(results["recruitment.Applicant"].affected, 1)
        a.refresh_from_db()
        self.assertEqual(a.first_name, "Alex")

    def test_delete_action_deletes_old_rejected_only(self):
        RetentionRule.objects.filter(entity_type="recruitment.Applicant").update(action=RetentionRule.Action.DELETE)
        old = self._applicant(Applicant.Stage.REJECTED, 14, email="old@example.com")
        keep = self._applicant(Applicant.Stage.HIRED, 14, email="hired@example.com")
        retention.run_retention(now=self.now)
        self.assertFalse(Applicant.objects.filter(pk=old.pk).exists())
        self.assertTrue(Applicant.objects.filter(pk=keep.pk).exists())

    def test_anonymise_also_deletes_the_resume_file(self):
        """M7 (HR_Code_report.md): an anonymised row that still points at
        the original person's CV on disk isn't actually anonymised."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        old_rejected = self._applicant(Applicant.Stage.REJECTED, 14, email="old@example.com")
        old_rejected.resume.save("cv.pdf", SimpleUploadedFile("cv.pdf", b"%PDF-1.7\ncv"), save=False)
        old_rejected.resume_content_type = "application/pdf"
        old_rejected.resume_size_bytes = 11
        old_rejected.save(update_fields=["resume", "resume_content_type", "resume_size_bytes"])
        stored_name = old_rejected.resume.name
        self.assertTrue(old_rejected.resume.storage.exists(stored_name))

        retention.run_retention(now=self.now)

        old_rejected.refresh_from_db()
        self.assertFalse(old_rejected.resume)
        self.assertEqual(old_rejected.resume_content_type, "")
        self.assertEqual(old_rejected.resume_size_bytes, 0)
        self.assertFalse(old_rejected.resume.storage.exists(stored_name))

    def test_delete_action_also_deletes_the_resume_file(self):
        """A bulk qs.delete() never calls FileField.delete() on its own --
        without the explicit per-row cleanup this would orphan the file."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        RetentionRule.objects.filter(entity_type="recruitment.Applicant").update(action=RetentionRule.Action.DELETE)
        old = self._applicant(Applicant.Stage.REJECTED, 14, email="old@example.com")
        # save=False + an update_fields-restricted save, not resume.save(save=True):
        # the latter calls a full applicant.save() with no update_fields, which
        # would reset updated_at (auto_now=True) and undo _applicant()'s backdating.
        old.resume.save("cv.pdf", SimpleUploadedFile("cv.pdf", b"%PDF-1.7\ncv"), save=False)
        old.save(update_fields=["resume"])
        storage = old.resume.storage
        stored_name = old.resume.name
        self.assertTrue(storage.exists(stored_name))

        retention.run_retention(now=self.now)

        self.assertFalse(Applicant.objects.filter(pk=old.pk).exists())
        self.assertFalse(storage.exists(stored_name))
