"""Retention handler for applicants (Data-Dictionary.md `retention_rule`
example: "unsuccessful applicants -> anonymise after 12 months").

Registered from RecruitmentConfig.ready(); executed by
rbac_audit.retention.run_retention. Only *rejected* applicants are in scope
— hired applicants became employees (their record is the hire audit trail)
and applicants still in the pipeline are live business data.

Anonymise keeps the row (and its stage outcome + demographics, which feed
aggregate EE recruitment reporting) but strips identifying fields, clears
free-text stage notes, and purges the simple-history rows that would
otherwise still hold the original PII. Delete removes the rows outright.
Both are idempotent (anonymised rows carry `anonymised_at`).
"""
from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from rbac_audit.models import RetentionRule

from .models import Applicant, ApplicantStageEvent

ANONYMISED_DOB = date(1900, 1, 1)


def _eligible(cutoff):
    return Applicant.objects.filter(
        current_stage=Applicant.Stage.REJECTED, updated_at__lt=cutoff, anonymised_at__isnull=True
    )


def anonymise_applicant(applicant: Applicant) -> None:
    applicant.first_name = "Anonymised"
    applicant.last_name = f"Applicant {applicant.pk}"
    applicant.email = f"anonymised-{applicant.pk}@invalid.local"
    applicant.phone = ""
    applicant.date_of_birth = ANONYMISED_DOB
    applicant.rejected_reason = ""
    applicant.anonymised_at = timezone.now()
    # Purge history first so the save() below records only the anonymised state.
    applicant.history.all().delete()
    applicant.save()
    ApplicantStageEvent.objects.filter(applicant=applicant).update(notes="")


def applicant_retention_handler(*, cutoff, action, dry_run) -> int:
    if action == RetentionRule.Action.DELETE:
        qs = Applicant.objects.filter(current_stage=Applicant.Stage.REJECTED, updated_at__lt=cutoff)
        if dry_run:
            return qs.count()
        with transaction.atomic():
            count = qs.count()
            qs.delete()
        return count
    if action == RetentionRule.Action.ANONYMISE:
        qs = _eligible(cutoff)
        if dry_run:
            return qs.count()
        count = 0
        for applicant in qs.iterator():
            with transaction.atomic():
                anonymise_applicant(applicant)
            count += 1
        return count
    return 0
