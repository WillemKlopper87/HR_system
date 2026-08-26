from __future__ import annotations

from datetime import timedelta

from core_hr.models import EmployeeVersion

from .constants import (
    AGGREGATE_ROW_KEYS,
    BARRIER_CATEGORIES,
    DEMOGRAPHIC_COLUMNS,
    OCCUPATIONAL_LEVEL_CODES,
    SKILLS_DEMOGRAPHIC_COLUMNS,
)
from .models import EEQuestionnaire, EEReport, EmployerConfig, RemunerationRecord

REQUIRED_EMPLOYER_FIELDS = [
    "trade_name", "dti_registration_number", "paye_sars_number", "uif_reference_number",
    "ee_reference_number", "ceo_name", "ee_senior_manager_name", "business_type",
]


def validate_report_readiness(*, form_type: str, report_year: int, period_start, period_end) -> list[str]:
    """Checks required for report GENERATION to be meaningful — the "no
    blank cells" rule (EEA-Form-Spec-Notes.md) is satisfied structurally
    by aggregation.py always filling zeros, so this focuses on the things
    a zero-filled matrix can't catch: missing employer identity, no
    questionnaire, no remuneration data, and the EEA2<->EEA4 cross-form
    headcount match."""
    issues: list[str] = []

    config = EmployerConfig.objects.first()
    if config is None:
        issues.append("Employer configuration (Section A) has not been captured yet.")
    else:
        missing = [f for f in REQUIRED_EMPLOYER_FIELDS if not getattr(config, f)]
        if missing:
            issues.append(f"Employer configuration is missing: {', '.join(missing)}.")

    if not EEQuestionnaire.objects.filter(report_year=report_year).exists():
        issues.append(f"No EE questionnaire captured for {report_year} yet.")

    if form_type == EEReport.FormType.EEA4:
        if not RemunerationRecord.objects.filter(period_start=period_start, period_end=period_end).exists():
            issues.append("No remuneration records imported for this reporting period.")
        issues.extend(_cross_form_headcount_issues(report_year))

    return issues


def _cross_form_headcount_issues(report_year: int) -> list[str]:
    """EEA-Form-Spec-Notes.md: "EEA4 workforce counts must exactly match
    EEA2 Section B counts per level/group — a cross-form validation
    rule." Only checkable once a current EEA2 exists for the same year;
    if none does, that itself is the issue."""
    from .aggregation import headcount_and_remuneration_matrix
    from .models import RemunerationRecord as RR

    eea2 = (
        EEReport.objects.filter(form_type=EEReport.FormType.EEA2, report_year=report_year)
        .exclude(status=EEReport.Status.SUPERSEDED)
        .order_by("-version")
        .first()
    )
    if eea2 is None:
        return ["No current EEA2 report exists for this year yet — generate it first (EEA4 headcounts must match EEA2 Section B)."]

    records = RR.objects.filter(period_start=eea2.period_start, period_end=eea2.period_end)
    if not records.exists():
        return []  # already flagged by the "no remuneration records" check above

    eea2_grand_total = eea2.data.get("workforce_profile", {}).get("grand_total", {})
    eea4_counts = headcount_and_remuneration_matrix(eea2.period_start, eea2.period_end, eea2.period_end)
    eea4_grand_total = eea4_counts["number_of_employees"].get("grand_total", {})

    mismatches = [
        col for col in DEMOGRAPHIC_COLUMNS if eea2_grand_total.get(col, 0) != eea4_grand_total.get(col, 0)
    ]
    if mismatches:
        return [
            "EEA4 headcount doesn't match EEA2 Section B for: " + ", ".join(mismatches) + " — "
            "likely means remuneration records are missing for some employees."
        ]
    return []


# --- H3: cell-by-cell validation of an already-generated snapshot ----------
# EEA-Form-Spec-Notes.md, "Consequences for the build" #7: "Validation
# engine rules confirmed: complete matrices (zeros not blanks), integer
# remuneration, EEA2<->EEA4 count consistency, annualisation, % row
# computation, temporary = <3 months." `validate_report_readiness` above
# gates GENERATION on data being available; this gates review/sign-off on
# the frozen `data` itself actually being correct — a report can still be
# wrong even when every precondition for generating one was satisfied (an
# aggregation bug, or source data that changed between "ready" and
# "generate").
#
# Annualisation isn't independently checkable here: RemunerationRecord
# stores only the final annualised figure (services.py::import_remuneration_
# csv — a CSV stand-in for the real SAP extract, ADR-006), not the raw
# pre-annualisation earnings or months-worked a recomputation would need.
#
# "% row computation" isn't a separate check either: this system's exports
# report values only (export.py's own note — "not a pixel-perfect
# recreation... a designated employer would still transcribe/upload this
# onto the actual submission form", where percentages get computed) —
# percentages are a trivial derived function of the values, so their
# correctness is fully covered by the aggregate-row arithmetic check below;
# there's no separate percentage storage to validate.

TEMPORARY_MAX_DAYS = 90  # "employed to work less than 3 months"

_EEA2_MATRIX_SECTIONS = [
    ("workforce_profile", DEMOGRAPHIC_COLUMNS),
    ("disability_workforce", DEMOGRAPHIC_COLUMNS),
    ("recruitment", DEMOGRAPHIC_COLUMNS),
    ("promotion", DEMOGRAPHIC_COLUMNS),
    ("termination", DEMOGRAPHIC_COLUMNS),
    ("skills_development", SKILLS_DEMOGRAPHIC_COLUMNS),
]
_EEA4_MATRIX_SECTIONS = [
    ("number_of_employees", DEMOGRAPHIC_COLUMNS),
    ("total_remuneration", DEMOGRAPHIC_COLUMNS),
]


def validate_report_data(report: EEReport) -> list[str]:
    """Cell-by-cell validation of an already-generated `EEReport.data`
    snapshot — see module-level note above for how this differs from
    `validate_report_readiness` and what "% row computation"/annualisation
    mean here specifically."""
    sections = _EEA2_MATRIX_SECTIONS if report.form_type == EEReport.FormType.EEA2 else _EEA4_MATRIX_SECTIONS
    issues: list[str] = []
    for key, columns in sections:
        matrix = report.data.get(key)
        if matrix is None:
            issues.append(f"{key}: section missing from the generated data entirely.")
            continue
        issues += _matrix_completeness_issues(key, matrix, columns)
        issues += _matrix_arithmetic_issues(key, matrix, columns)

    if report.form_type == EEReport.FormType.EEA4:
        issues += _integer_remuneration_issues(report)
        issues += _frozen_cross_form_headcount_issues(report)
    else:
        issues += _barrier_grid_completeness_issues(report)
        issues += _consultation_evidence_issues(report)
        issues += _measure_evidence_issues(report)
        issues += _shortfall_justification_issues(report)

    issues += _temporary_classification_issues(report)
    return issues


# --- C6 (design spec 2026-08-26 §3.4): Section F evidence checks -----------
# Validate, don't derive: the frozen questionnaire's Y/N answers stay the
# employer's own declaration; these findings say where the live forum/plan
# records don't back them up (or back up an answer that says "No").
# Advisory only — never part of validate_report_readiness, so a missing
# forum record can't block generating the draft that surfaces it.


def _consultation_evidence_issues(report: EEReport) -> list[str]:
    from .models import EEForumMeeting

    consultation = (report.data.get("questionnaire") or {}).get("consultation") or {}
    claimed = consultation.get("consultative_body_or_ee_forum")
    meetings = EEForumMeeting.objects.filter(report_year=report.report_year).count()
    if claimed is True and meetings == 0:
        return [
            f"Section F claims consultation with the EE forum, but no forum meeting is on record for {report.report_year}."
        ]
    if not claimed and meetings > 0:
        return [
            f"Section F says the EE forum was not consulted, but {meetings} forum meeting(s) are on record for "
            f"{report.report_year} — check the answer."
        ]
    return []


def _measure_evidence_issues(report: EEReport) -> list[str]:
    from .models import EEPlan, EEPlanMeasure

    plan = (
        EEPlan.objects.filter(plan_period_start__lte=report.period_end, plan_period_end__gte=report.period_end)
        .order_by("-plan_period_start")
        .first()
    )
    if plan is None:
        return []  # no plan at all is its own (readiness/dashboard) problem, not a grid mismatch
    barriers = (report.data.get("questionnaire") or {}).get("barriers") or {}
    categories_with_measures = set(EEPlanMeasure.objects.filter(plan=plan).values_list("category", flat=True))
    issues = []
    for key, label in BARRIER_CATEGORIES:
        entry = barriers.get(key) if isinstance(barriers.get(key), dict) else {}
        claimed = entry.get("aa_measures") is True
        if claimed and key not in categories_with_measures:
            issues.append(f"Section F: '{label}' claims affirmative-action measures, but the EE plan has no measure in that category.")
        elif not claimed and key in categories_with_measures:
            issues.append(f"Section F: '{label}' answers No to affirmative-action measures, but the EE plan has one on record.")
    return issues


def _shortfall_justification_issues(report: EEReport) -> list[str]:
    """EE Regs 2025 reg. 16(5) / EEA2 Section B: a level short of its annual
    target needs a justifiable reason ticked for that level. Uses the same
    percentage-point gap the dashboard/snapshots use, against the plan
    covering the report's period end."""
    from .dashboards import _target_gap
    from .models import EEPlan

    plan = (
        EEPlan.objects.filter(plan_period_start__lte=report.period_end, plan_period_end__gte=report.period_end)
        .order_by("-plan_period_start")
        .first()
    )
    if plan is None or not plan.annual_targets:
        return []
    workforce = report.data.get("workforce_profile") or {}
    gap = _target_gap(workforce, plan.annual_targets)
    reasons = (report.data.get("questionnaire") or {}).get("justifiable_reasons") or {}
    issues = []
    for level in OCCUPATIONAL_LEVEL_CODES:
        if not any(isinstance(v, int) and v > 0 for v in (workforce.get(level) or {}).values()):
            continue  # no one at this level: a 0% "shortfall" against a target is noise, not a finding
        short = [col for col, value in gap.get(level, {}).items() if value < 0]
        if short and not reasons.get(level):
            issues.append(
                f"Section B: {level} is below its annual target for {', '.join(short)} but no justifiable reason is "
                "recorded for that level."
            )
    return issues


def _matrix_completeness_issues(key: str, matrix: dict, columns: list[str]) -> list[str]:
    """"No blank cells, N/A or dashes allowed — zeros must be captured as
    0." Every row x column must be a present, non-negative whole number."""
    issues = []
    for row in OCCUPATIONAL_LEVEL_CODES + AGGREGATE_ROW_KEYS:
        row_values = matrix.get(row)
        if row_values is None:
            issues.append(f"{key}: row '{row}' is missing entirely.")
            continue
        for col in columns:
            value = row_values.get(col)
            if value is None:
                issues.append(f"{key}[{row}][{col}]: cell is missing (must be 0, not blank).")
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                issues.append(f"{key}[{row}][{col}]: expected a non-negative whole number, got {value!r}.")
    return issues


def _matrix_arithmetic_issues(key: str, matrix: dict, columns: list[str]) -> list[str]:
    """Aggregate rows must actually be the sum of what they claim to
    aggregate — catches drift between an occupational-level breakdown and
    its own totals row without needing a human to re-add the column."""
    issues = []
    for col in columns:
        try:
            level_sum = sum(matrix[level][col] for level in OCCUPATIONAL_LEVEL_CODES)
            total_permanent = matrix["total_permanent"][col]
            temporary = matrix["temporary_employees"][col]
            grand_total = matrix["grand_total"][col]
        except (KeyError, TypeError):
            continue  # already reported by _matrix_completeness_issues
        if total_permanent != level_sum:
            issues.append(
                f"{key}[total_permanent][{col}] = {total_permanent}, but the occupational-level rows sum to {level_sum}."
            )
        if grand_total != total_permanent + temporary:
            issues.append(
                f"{key}[grand_total][{col}] = {grand_total}, expected total_permanent + temporary_employees "
                f"= {total_permanent + temporary}."
            )
    return issues


def _is_whole_rand(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _integer_remuneration_issues(report: EEReport) -> list[str]:
    """"Captured as whole Rands, no separators or decimals." Walks every
    Rand-shaped figure in an EEA4 snapshot."""
    issues = []
    totals = report.data.get("total_remuneration", {})
    for row, cols in totals.items():
        for col, value in cols.items():
            if not _is_whole_rand(value):
                issues.append(f"total_remuneration[{row}][{col}]: expected a whole Rand amount, got {value!r}.")

    def _check_entry(label: str, entry) -> None:
        if not isinstance(entry, dict):
            return
        for field in ("fixed", "variable", "total"):
            value = entry.get(field)
            if value is not None and not _is_whole_rand(value):
                issues.append(f"{label}[{field}]: expected a whole Rand amount, got {value!r}.")

    highest = report.data.get("highest_paid", {})
    for level_code, by_col in highest.items():
        for col, entry in by_col.items():
            _check_entry(f"highest_paid[{level_code}][{col}]", entry)

    lowest = report.data.get("lowest_paid_lowest_level", {})
    for col, entry in lowest.items():
        _check_entry(f"lowest_paid_lowest_level[{col}]", entry)

    gap = report.data.get("median_and_gap", {})
    median = gap.get("median_remuneration")
    if median is not None and not _is_whole_rand(median):
        issues.append(f"median_and_gap[median_remuneration]: expected a whole Rand amount, got {median!r}.")
    for bucket in ("top_5_pct", "bottom_5_pct"):
        bucket_data = gap.get(bucket) or {}
        for field in ("total", "range_low", "range_high"):
            value = bucket_data.get(field)
            if value is not None and not _is_whole_rand(value):
                issues.append(f"median_and_gap[{bucket}][{field}]: expected a whole Rand amount, got {value!r}.")
    return issues


def _frozen_cross_form_headcount_issues(report: EEReport) -> list[str]:
    """Same rule as `_cross_form_headcount_issues` above, applied to the
    archive itself rather than live data: the EEA4 being validated must
    still agree with whatever current EEA2 exists for the same
    report_year — two frozen snapshots can drift apart if one was
    regenerated after data changed and the other wasn't."""
    eea2 = (
        EEReport.objects.filter(form_type=EEReport.FormType.EEA2, report_year=report.report_year)
        .exclude(status=EEReport.Status.SUPERSEDED)
        .order_by("-version")
        .first()
    )
    if eea2 is None:
        return []  # already flagged by validate_report_readiness before generation was even allowed

    eea2_grand_total = eea2.data.get("workforce_profile", {}).get("grand_total", {})
    eea4_grand_total = report.data.get("number_of_employees", {}).get("grand_total", {})
    mismatches = [
        col for col in DEMOGRAPHIC_COLUMNS if eea2_grand_total.get(col, 0) != eea4_grand_total.get(col, 0)
    ]
    if not mismatches:
        return []
    return [f"EEA4 v{report.version} headcount doesn't match EEA2 v{eea2.version}'s Section B for: " + ", ".join(mismatches) + "."]


def _barrier_grid_completeness_issues(report: EEReport) -> list[str]:
    """Section F: all 24 fixed barrier/AA categories must have an actual
    Y/N answer for both "barriers" and "aa_measures" — a category silently
    missing from the questionnaire reads as "not asked", not "No"."""
    barriers = (report.data.get("questionnaire") or {}).get("barriers") or {}
    issues = []
    for key, label in BARRIER_CATEGORIES:
        entry = barriers.get(key)
        if not isinstance(entry, dict):
            issues.append(f"Barriers & AA measures grid (Section F): '{label}' has not been answered at all.")
            continue
        for field in ("barriers", "aa_measures"):
            if not isinstance(entry.get(field), bool):
                issues.append(f"Barriers & AA measures grid (Section F): '{label}' is missing a Y/N answer for '{field}'.")
    return issues


def _temporary_classification_issues(report: EEReport) -> list[str]:
    """"Temporary employee = employed to work less than 3 months."
    `employment_status=TEMPORARY` is a manually-chosen classification
    (core_hr has no separate contract-duration field) — cross-checked here
    against how long the employee's version has actually been open as of
    this report's period_end, the same as_of_date `generate_report` uses by
    default. Applies to either form type — this is an employee-data
    correctness check, not something specific to one matrix."""
    as_of = report.period_end
    cutoff = as_of - timedelta(days=TEMPORARY_MAX_DAYS)
    issues = []
    versions = (
        EmployeeVersion.objects.as_at(as_of)
        .filter(employment_status=EmployeeVersion.EmploymentStatus.TEMPORARY, valid_from__lt=cutoff)
        .select_related("employee")
    )
    for version in versions:
        days_open = (as_of - version.valid_from).days
        issues.append(
            f"{version.employee.employee_number} is classified Temporary (<3 months) but has been in that "
            f"version since {version.valid_from} ({days_open} days as of {as_of})."
        )
    return issues
