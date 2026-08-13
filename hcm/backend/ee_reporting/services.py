from __future__ import annotations

import csv
import io
from datetime import date

from core_hr.models import Employee
from django.db import transaction
from django.utils import timezone

from . import aggregation
from .models import EEQuestionnaire, EEReport, EmployerConfig, RemunerationRecord
from .validation import validate_report_readiness


class ReportNotReadyError(ValueError):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


class ApprovalError(ValueError):
    pass


class RemunerationImportError(ValueError):
    pass


def _build_eea2_data(*, period_start, period_end, as_of_date, report_year) -> dict:
    config = EmployerConfig.objects.first()
    questionnaire = EEQuestionnaire.objects.filter(report_year=report_year).first()
    return {
        "employer": _serialize_employer(config),
        "questionnaire": _serialize_questionnaire(questionnaire),
        "workforce_profile": aggregation.workforce_profile_matrix(as_of_date),
        "disability_workforce": aggregation.disability_workforce_matrix(as_of_date),
        "recruitment": aggregation.movement_matrix("hire", period_start, period_end),
        "promotion": aggregation.movement_matrix("promotion", period_start, period_end),
        "termination": aggregation.movement_matrix("termination", period_start, period_end),
        "skills_development": aggregation.skills_development_matrix(period_start, period_end, as_of_date),
    }


def _build_eea4_data(*, period_start, period_end, as_of_date) -> dict:
    config = EmployerConfig.objects.first()
    questionnaire = EEQuestionnaire.objects.filter(report_year=period_end.year).first()
    return {
        "employer": _serialize_employer(config),
        "questionnaire": _serialize_questionnaire(questionnaire),
        **aggregation.headcount_and_remuneration_matrix(period_start, period_end, as_of_date),
        **aggregation.highest_and_lowest_paid_by_level(period_start, period_end, as_of_date),
        "median_and_gap": aggregation.median_and_gap_stats(period_start, period_end),
    }


def _serialize_employer(config) -> dict:
    if config is None:
        return {}
    return {
        field.name: str(getattr(config, field.name))
        for field in config._meta.fields
        if field.name not in ("id", "created_at", "updated_at")
    }


def _serialize_questionnaire(questionnaire) -> dict:
    if questionnaire is None:
        return {}
    return {
        field.name: str(getattr(questionnaire, field.name)) if not isinstance(getattr(questionnaire, field.name), (dict, bool, type(None))) else getattr(questionnaire, field.name)
        for field in questionnaire._meta.fields
        if field.name not in ("id", "created_at", "updated_at", "updated_by")
    }


@transaction.atomic
def generate_report(
    *, form_type: str, report_year: int, period_start, period_end, actor=None, as_of_date=None
) -> EEReport:
    """Materialises a new immutable version — Architecture-Design.md
    §5.1's "frozen snapshot" — from whatever core_hr/learning/
    RemunerationRecord data exists right now. Any prior version of the
    SAME form_type+report_year that hasn't been signed off yet is marked
    SUPERSEDED; a signed-off version is left untouched (the archive)."""
    as_of_date = as_of_date or period_end

    issues = validate_report_readiness(
        form_type=form_type, report_year=report_year, period_start=period_start, period_end=period_end
    )
    if issues:
        raise ReportNotReadyError(issues)

    if form_type == EEReport.FormType.EEA2:
        data = _build_eea2_data(period_start=period_start, period_end=period_end, as_of_date=as_of_date, report_year=report_year)
    else:
        data = _build_eea4_data(period_start=period_start, period_end=period_end, as_of_date=as_of_date)

    (
        EEReport.objects.filter(form_type=form_type, report_year=report_year)
        .exclude(status=EEReport.Status.SIGNED_OFF)
        .exclude(status=EEReport.Status.SUPERSEDED)
        .update(status=EEReport.Status.SUPERSEDED)
    )
    next_version = (
        EEReport.objects.filter(form_type=form_type, report_year=report_year).count() + 1
    )
    return EEReport.objects.create(
        form_type=form_type, report_year=report_year, version=next_version,
        period_start=period_start, period_end=period_end, data=data, generated_by=actor,
    )


def submit_for_review(report: EEReport, *, actor=None) -> EEReport:
    if report.status != EEReport.Status.DRAFT:
        raise ApprovalError("Only a draft report can be submitted for EE manager review.")
    report.status = EEReport.Status.PENDING_EE_REVIEW
    report.save(update_fields=["status"])
    return report


def ee_manager_approve(report: EEReport, *, actor) -> EEReport:
    if report.status != EEReport.Status.PENDING_EE_REVIEW:
        raise ApprovalError("Only a report pending EE manager review can be approved at this step.")
    report.status = EEReport.Status.PENDING_SIGNOFF
    report.ee_reviewed_by = actor
    report.ee_reviewed_at = timezone.now()
    report.save(update_fields=["status", "ee_reviewed_by", "ee_reviewed_at"])
    return report


def sign_off(report: EEReport, *, actor, place: str = "") -> EEReport:
    if report.status != EEReport.Status.PENDING_SIGNOFF:
        raise ApprovalError("Only a report pending sign-off can be signed off.")
    report.status = EEReport.Status.SIGNED_OFF
    report.signed_off_by = actor
    report.signed_off_at = timezone.now()
    report.signed_off_place = place
    report.save(update_fields=["status", "signed_off_by", "signed_off_at", "signed_off_place"])
    return report


REMUNERATION_CSV_HEADER = ["employee_number", "period_start", "period_end", "fixed_remuneration", "variable_remuneration"]


@transaction.atomic
def import_remuneration_csv(csv_text: str, *, actor=None) -> dict:
    """Stand-in for the real SAP payroll extract (ADR-006 notes it as a
    future Sprint 12b interface) — same "build the seam, defer the
    vendor" pattern as assessments/identity_verification. Expected
    columns: employee_number, period_start, period_end (YYYY-MM-DD),
    fixed_remuneration, variable_remuneration (whole Rand each)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    missing_columns = [c for c in REMUNERATION_CSV_HEADER if c not in (reader.fieldnames or [])]
    if missing_columns:
        raise RemunerationImportError(f"CSV is missing columns: {', '.join(missing_columns)}.")

    created, updated, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        try:
            employee = Employee.objects.get(employee_number=row["employee_number"].strip())
            period_start = date.fromisoformat(row["period_start"].strip())
            period_end = date.fromisoformat(row["period_end"].strip())
            fixed = int(row["fixed_remuneration"])
            variable = int(row["variable_remuneration"] or 0)
        except Employee.DoesNotExist:
            errors.append(f"Row {i}: no employee with number {row['employee_number']!r}.")
            continue
        except (ValueError, KeyError) as exc:
            errors.append(f"Row {i}: {exc}")
            continue

        _, was_created = RemunerationRecord.objects.update_or_create(
            employee=employee, period_start=period_start, period_end=period_end,
            defaults={"fixed_remuneration": fixed, "variable_remuneration": variable, "imported_by": actor},
        )
        created += was_created
        updated += not was_created

    return {"created": created, "updated": updated, "errors": errors}
