from __future__ import annotations

import csv
import io
from datetime import date

from core_hr.models import Employee
from django.db import models, transaction
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


# --- C6: consultation forum + plan monitoring (design spec 2026-08-26) ----


def is_designated_group(version) -> bool | None:
    """EEA s.1 "designated groups": Black people (African/Coloured/Indian),
    women, people with disabilities — citizens only. None when the version
    can't be classified (undisclosed race/gender, or a foreign national,
    who the form doesn't race)."""
    from core_hr.models import EmployeeVersion

    if version.citizenship_status == EmployeeVersion.CitizenshipStatus.FOREIGN_NATIONAL:
        return None
    if version.disability_status == EmployeeVersion.DisabilityStatus.YES:
        return True
    if version.race == EmployeeVersion.Race.NOT_DISCLOSED or version.gender == EmployeeVersion.Gender.NOT_DISCLOSED:
        return None
    return version.race != EmployeeVersion.Race.WHITE or version.gender == EmployeeVersion.Gender.FEMALE


def forum_composition(as_of=None) -> dict:
    """Derived, never stored (spec §3.3): does the active forum reflect
    every occupational level present in the workforce and both designated
    and non-designated employees (EEA s.16(2))? Returns booleans and level
    codes only — a forum is ~5-15 people, so any per-demographic count of
    it would be a small cell by construction."""
    from core_hr.models import EmployeeVersion

    from .constants import OCCUPATIONAL_LEVEL_CODES
    from .models import EEForumMember

    as_of = as_of or timezone.localdate()
    members = [
        m for m in EEForumMember.objects.select_related("employee")
        .filter(term_start__lte=as_of)
        .filter(models.Q(term_end__isnull=True) | models.Q(term_end__gte=as_of))
    ]
    workforce_levels = set(
        EmployeeVersion.objects.as_at(as_of)
        .values_list("occupational_level__code", flat=True)
        .distinct()
    ) & set(OCCUPATIONAL_LEVEL_CODES)

    covered_levels: set[str] = set()
    designated = non_designated = False
    by_representation = {key: 0 for key, _ in EEForumMember.Representation.choices}
    for member in members:
        by_representation[member.representation] += 1
        version = member.employee.current_version
        if version is None:
            continue
        covered_levels.add(version.occupational_level.code)
        flag = is_designated_group(version)
        if flag is True:
            designated = True
        elif flag is False:
            non_designated = True

    uncovered = [code for code in OCCUPATIONAL_LEVEL_CODES if code in workforce_levels and code not in covered_levels]
    return {
        "as_of": as_of,
        "active_member_count": len(members),
        "by_representation": by_representation,
        "levels_in_workforce": [c for c in OCCUPATIONAL_LEVEL_CODES if c in workforce_levels],
        "levels_uncovered": uncovered,
        "designated_groups_represented": designated,
        "non_designated_represented": non_designated,
        "union_nominated_present": by_representation[EEForumMember.Representation.UNION_NOMINATED] > 0,
        "adequate": not uncovered and designated and non_designated and bool(members),
    }


_DESIGNATED_MALE = ["african_male", "coloured_male", "indian_male"]
_DESIGNATED_FEMALE = ["african_female", "coloured_female", "indian_female", "white_female"]


def _designated_group_pct(workforce: dict) -> dict:
    """Per level: designated-group share by gender, the shape the 2025
    sector-target determination uses (male / female / total designated —
    white males without disabilities and foreign nationals excluded)."""
    from .constants import DEMOGRAPHIC_COLUMNS, OCCUPATIONAL_LEVEL_CODES

    out = {}
    for level in OCCUPATIONAL_LEVEL_CODES:
        row = workforce.get(level, {})
        total = sum(row.get(c, 0) for c in DEMOGRAPHIC_COLUMNS)
        if not total:
            out[level] = {"male": 0.0, "female": 0.0, "total": 0.0}
            continue
        male = round(sum(row.get(c, 0) for c in _DESIGNATED_MALE) / total * 100, 1)
        female = round(sum(row.get(c, 0) for c in _DESIGNATED_FEMALE) / total * 100, 1)
        out[level] = {"male": male, "female": female, "total": round(male + female, 1)}
    return out


def _sector_gap(designated_pct: dict, sector_targets: dict, numerical_goals: dict, workforce: dict) -> dict:
    """Sector targets can be captured either in the gazette's own shape
    ({level: {"male": pct, "female": pct[, "total": pct]}}) or as per-column
    percentages like annual_targets — handled per level, whichever the row
    uses. numerical_goals (semi/unskilled, reg. 9(12)) are merged in."""
    from .dashboards import _target_gap

    merged = {**(sector_targets or {}), **(numerical_goals or {})}
    gazette_shape = {lvl: t for lvl, t in merged.items() if isinstance(t, dict) and ("male" in t or "female" in t)}
    column_shape = {lvl: t for lvl, t in merged.items() if lvl not in gazette_shape}
    gap = _target_gap(workforce, column_shape) if column_shape else {}
    for level, target in gazette_shape.items():
        actual = designated_pct.get(level, {})
        gap[level] = {
            key: round(actual.get(key, 0.0) - float(target[key]), 1) for key in ("male", "female", "total") if key in target
        }
    return gap


@transaction.atomic
def take_progress_snapshot(plan, *, as_of=None, actor=None, note: str = ""):
    """Freezes today's (or `as_of`'s) workforce profile against the plan's
    targets — spec §4.2 for why this is stored rather than recomputed. The
    matrices come from the same aggregation functions EEReport uses, so a
    snapshot and a report for the same date agree by construction."""
    from decimal import Decimal

    from .constants import DEMOGRAPHIC_COLUMNS, OCCUPATIONAL_LEVEL_CODES
    from .dashboards import _target_gap
    from .models import EEPlanProgressSnapshot

    as_of = as_of or timezone.localdate()
    if not (plan.plan_period_start <= as_of <= plan.plan_period_end):
        raise ValueError(f"{as_of} is outside the plan period {plan.plan_period_start}–{plan.plan_period_end}.")
    if EEPlanProgressSnapshot.objects.filter(plan=plan, as_of=as_of).exists():
        raise ValueError(f"A snapshot for {as_of} already exists on this plan.")

    workforce = aggregation.workforce_profile_matrix(as_of)
    disability = aggregation.disability_workforce_matrix(as_of)
    designated_pct = _designated_group_pct(workforce)
    annual_gap = _target_gap(workforce, plan.annual_targets or {})
    eap_gap = _target_gap(workforce, plan.eap_profile or {})
    sector_gap = _sector_gap(designated_pct, plan.sector_targets, plan.numerical_goals, workforce)

    total_headcount = sum(workforce.get("grand_total", {}).get(c, 0) for c in DEMOGRAPHIC_COLUMNS)
    disabled_headcount = sum(disability.get("grand_total", {}).get(c, 0) for c in DEMOGRAPHIC_COLUMNS)
    disability_pct = (
        Decimal(disabled_headcount * 100 / total_headcount).quantize(Decimal("0.01")) if total_headcount else None
    )

    flags = []
    for level in OCCUPATIONAL_LEVEL_CODES:
        for col, gap in annual_gap.get(level, {}).items():
            if gap < 0:
                flags.append({"row": level, "col": col, "basis": "annual_target_shortfall", "gap_pct": gap})
        for col, gap in eap_gap.get(level, {}).items():
            if gap > 0:
                flags.append({"row": level, "col": col, "basis": "over_eap", "gap_pct": gap})
    if disability_pct is not None and plan.disability_5yr_target_pct is not None and disability_pct < plan.disability_5yr_target_pct:
        flags.append({
            "row": "grand_total", "col": "disability", "basis": "disability_target_shortfall",
            "gap_pct": float(disability_pct - plan.disability_5yr_target_pct),
        })

    return EEPlanProgressSnapshot.objects.create(
        plan=plan, as_of=as_of, workforce_profile=workforce, disability_workforce=disability,
        annual_target_gap_pct=annual_gap, sector_target_gap_pct=sector_gap, eap_gap_pct=eap_gap,
        designated_group_pct=designated_pct, disability_pct=disability_pct, flags=flags, note=note, taken_by=actor,
    )
