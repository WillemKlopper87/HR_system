"""H3 org-wide data-quality sweep: critical-post-with-no-ready-successor
check (spec §2.9), registered from SuccessionConfig.ready()."""
from __future__ import annotations

from core_hr.data_quality import run_data_quality_checks
from core_hr.models import DataQualityException
from django.test import TestCase

from .data_quality import critical_post_no_successor_handler
from .models import CriticalPost, SuccessionCandidate
from .tests import SuccessionModelTestCase


class CriticalPostNoSuccessorHandlerTests(SuccessionModelTestCase):
    def test_occupied_critical_post_with_no_candidates_is_flagged(self):
        occupant = self._hire("E0200")
        self._occupy(self.position, occupant)
        CriticalPost.objects.create(position=self.position, reason="x")

        flagged = [emp for emp, _ in critical_post_no_successor_handler()]
        self.assertEqual(flagged, [occupant])

    def test_occupied_critical_post_with_a_ready_now_candidate_is_not_flagged(self):
        occupant = self._hire("E0201")
        self._occupy(self.position, occupant)
        critical_post = CriticalPost.objects.create(position=self.position, reason="x")
        successor = self._hire("E0202")
        SuccessionCandidate.objects.create(
            critical_post=critical_post, employee=successor, readiness=SuccessionCandidate.Readiness.READY_NOW,
        )

        self.assertEqual(list(critical_post_no_successor_handler()), [])

    def test_a_development_needed_only_candidate_still_flags(self):
        occupant = self._hire("E0203")
        self._occupy(self.position, occupant)
        critical_post = CriticalPost.objects.create(position=self.position, reason="x")
        successor = self._hire("E0204")
        SuccessionCandidate.objects.create(
            critical_post=critical_post, employee=successor,
            readiness=SuccessionCandidate.Readiness.DEVELOPMENT_NEEDED,
        )

        flagged = [emp for emp, _ in critical_post_no_successor_handler()]
        self.assertEqual(flagged, [occupant])

    def test_vacant_critical_post_is_silently_skipped(self):
        CriticalPost.objects.create(position=self.position, reason="x")
        self.assertEqual(list(critical_post_no_successor_handler()), [])

    def test_inactive_critical_post_is_not_considered(self):
        occupant = self._hire("E0205")
        self._occupy(self.position, occupant)
        flag = CriticalPost.objects.create(position=self.position, reason="x")
        flag.active = False
        flag.save(update_fields=["active"])

        self.assertEqual(list(critical_post_no_successor_handler()), [])

    def test_withdrawn_candidate_does_not_count(self):
        occupant = self._hire("E0206")
        self._occupy(self.position, occupant)
        critical_post = CriticalPost.objects.create(position=self.position, reason="x")
        successor = self._hire("E0207")
        candidate = SuccessionCandidate.objects.create(
            critical_post=critical_post, employee=successor, readiness=SuccessionCandidate.Readiness.READY_NOW,
        )
        candidate.active = False
        candidate.save(update_fields=["active"])

        flagged = [emp for emp, _ in critical_post_no_successor_handler()]
        self.assertEqual(flagged, [occupant])

    def test_wired_into_the_org_wide_sweep(self):
        occupant = self._hire("E0208")
        self._occupy(self.position, occupant)
        CriticalPost.objects.create(position=self.position, reason="x")

        run_data_quality_checks()

        self.assertTrue(
            DataQualityException.objects.filter(
                employee=occupant,
                exception_type=DataQualityException.ExceptionType.CRITICAL_POST_NO_SUCCESSOR,
                resolved_at__isnull=True,
            ).exists()
        )

    def test_sweep_auto_resolves_once_a_ready_successor_is_added(self):
        occupant = self._hire("E0209")
        self._occupy(self.position, occupant)
        critical_post = CriticalPost.objects.create(position=self.position, reason="x")

        run_data_quality_checks()
        self.assertTrue(
            DataQualityException.objects.filter(
                employee=occupant, exception_type=DataQualityException.ExceptionType.CRITICAL_POST_NO_SUCCESSOR,
                resolved_at__isnull=True,
            ).exists()
        )

        successor = self._hire("E0210")
        SuccessionCandidate.objects.create(
            critical_post=critical_post, employee=successor, readiness=SuccessionCandidate.Readiness.READY_1_2_YEARS,
        )
        run_data_quality_checks()
        self.assertFalse(
            DataQualityException.objects.filter(
                employee=occupant, exception_type=DataQualityException.ExceptionType.CRITICAL_POST_NO_SUCCESSOR,
                resolved_at__isnull=True,
            ).exists()
        )
