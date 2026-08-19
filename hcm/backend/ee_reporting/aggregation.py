from __future__ import annotations

from core_hr.models import EmployeeVersion, EmploymentEvent
# Architecture-Design.md §4: read learning's data through its query
# interface, not learning.models directly — ee_reporting may not import
# a peer module.
from learning.queries import employee_ids_with_completed_training_in_period

from .constants import (
    AGGREGATE_ROW_KEYS,
    DEMOGRAPHIC_COLUMNS,
    OCCUPATIONAL_LEVEL_CODES,
    SKILLS_DEMOGRAPHIC_COLUMNS,
    empty_matrix,
)
from .models import RemunerationRecord


def demographic_column(version) -> str | None:
    """Maps an EmployeeVersion's race/gender/citizenship to one of the 10
    EEA demographic columns. Returns None for not-disclosed race/gender —
    the form has no cell for "undisclosed"; an organisation with
    undisclosed demographics has a real data-quality problem the
    validation engine should surface (validation.py), not silently drop
    or misallocate."""
    if version.citizenship_status == EmployeeVersion.CitizenshipStatus.FOREIGN_NATIONAL:
        if version.gender == EmployeeVersion.Gender.MALE:
            return "foreign_national_male"
        if version.gender == EmployeeVersion.Gender.FEMALE:
            return "foreign_national_female"
        return None
    if version.race == EmployeeVersion.Race.NOT_DISCLOSED or version.gender == EmployeeVersion.Gender.NOT_DISCLOSED:
        return None
    gender_suffix = "male" if version.gender == EmployeeVersion.Gender.MALE else "female"
    return f"{version.race}_{gender_suffix}"


def _fill_aggregate_rows(matrix: dict) -> None:
    for level_code in OCCUPATIONAL_LEVEL_CODES:
        for col in DEMOGRAPHIC_COLUMNS:
            matrix["total_permanent"][col] += matrix[level_code][col]
    for col in DEMOGRAPHIC_COLUMNS:
        matrix["grand_total"][col] = matrix["total_permanent"][col] + matrix["temporary_employees"][col]


def _matrix_from_versions(versions_qs) -> dict:
    matrix = empty_matrix()
    for version in versions_qs.select_related("occupational_level"):
        level_code = version.occupational_level.code
        if level_code not in OCCUPATIONAL_LEVEL_CODES:
            continue
        col = demographic_column(version)
        if col is None:
            continue
        row_key = (
            "temporary_employees"
            if version.employment_status == EmployeeVersion.EmploymentStatus.TEMPORARY
            else level_code
        )
        matrix[row_key][col] += 1
    _fill_aggregate_rows(matrix)
    return matrix


def workforce_profile_matrix(as_of_date) -> dict:
    """EEA2 Section B, table 1.1."""
    return _matrix_from_versions(EmployeeVersion.objects.as_at(as_of_date))


def disability_workforce_matrix(as_of_date) -> dict:
    """EEA2 Section B, disability-only table."""
    return _matrix_from_versions(
        EmployeeVersion.objects.as_at(as_of_date).filter(disability_status=EmployeeVersion.DisabilityStatus.YES)
    )


def movement_matrix(event_type: str, period_start, period_end) -> dict:
    """EEA2 Section C — recruitment/promotion/termination, keyed by
    core_hr.EmploymentEvent.EventType. Demographics/level are read from
    to_version where available (the state the event created), falling
    back to from_version (e.g. termination has no to_version)."""
    matrix = empty_matrix()
    events = EmploymentEvent.objects.filter(
        event_type=event_type, effective_date__gte=period_start, effective_date__lte=period_end
    ).select_related(
        "to_version__occupational_level", "from_version__occupational_level",
    )
    for event in events:
        version = event.to_version or event.from_version
        if version is None:
            continue
        level_code = version.occupational_level.code
        if level_code not in OCCUPATIONAL_LEVEL_CODES:
            continue
        col = demographic_column(version)
        if col is None:
            continue
        row_key = (
            "temporary_employees"
            if version.employment_status == EmployeeVersion.EmploymentStatus.TEMPORARY
            else level_code
        )
        matrix[row_key][col] += 1
    _fill_aggregate_rows(matrix)
    return matrix


def skills_development_matrix(period_start, period_end, as_of_date) -> dict:
    """EEA2 Section D — no Foreign National columns on this table."""
    trained_ids = employee_ids_with_completed_training_in_period(period_start, period_end)
    matrix = {row: dict.fromkeys(SKILLS_DEMOGRAPHIC_COLUMNS, 0) for row in OCCUPATIONAL_LEVEL_CODES + AGGREGATE_ROW_KEYS}
    if not trained_ids:
        return matrix
    versions = EmployeeVersion.objects.as_at(as_of_date).filter(employee_id__in=trained_ids).select_related(
        "occupational_level"
    )
    for version in versions:
        level_code = version.occupational_level.code
        if level_code not in OCCUPATIONAL_LEVEL_CODES:
            continue
        col = demographic_column(version)
        if col is None or col not in SKILLS_DEMOGRAPHIC_COLUMNS:
            continue
        row_key = (
            "temporary_employees"
            if version.employment_status == EmployeeVersion.EmploymentStatus.TEMPORARY
            else level_code
        )
        matrix[row_key][col] += 1
    for level_code in OCCUPATIONAL_LEVEL_CODES:
        for col in SKILLS_DEMOGRAPHIC_COLUMNS:
            matrix["total_permanent"][col] += matrix[level_code][col]
    for col in SKILLS_DEMOGRAPHIC_COLUMNS:
        matrix["grand_total"][col] = matrix["total_permanent"][col] + matrix["temporary_employees"][col]
    return matrix


def _remuneration_for_period(period_start, period_end):
    return RemunerationRecord.objects.filter(
        period_start=period_start, period_end=period_end
    ).select_related("employee")


def headcount_and_remuneration_matrix(period_start, period_end, as_of_date) -> dict:
    """EEA4 Section C — number of employees + total remuneration per
    level/group. Must reconcile with EEA2 Section B's headcount per the
    cross-form validation rule (validation.py)."""
    counts = {row: dict.fromkeys(DEMOGRAPHIC_COLUMNS, 0) for row in OCCUPATIONAL_LEVEL_CODES + AGGREGATE_ROW_KEYS}
    totals = {row: dict.fromkeys(DEMOGRAPHIC_COLUMNS, 0) for row in OCCUPATIONAL_LEVEL_CODES + AGGREGATE_ROW_KEYS}

    records = _remuneration_for_period(period_start, period_end)
    version_by_employee = {
        v.employee_id: v
        for v in EmployeeVersion.objects.as_at(as_of_date).select_related("occupational_level").filter(
            employee_id__in=[r.employee_id for r in records]
        )
    }
    for record in records:
        version = version_by_employee.get(record.employee_id)
        if version is None:
            continue
        level_code = version.occupational_level.code
        if level_code not in OCCUPATIONAL_LEVEL_CODES:
            continue
        col = demographic_column(version)
        if col is None:
            continue
        row_key = (
            "temporary_employees"
            if version.employment_status == EmployeeVersion.EmploymentStatus.TEMPORARY
            else level_code
        )
        counts[row_key][col] += 1
        totals[row_key][col] += record.total_remuneration

    for level_code in OCCUPATIONAL_LEVEL_CODES:
        for col in DEMOGRAPHIC_COLUMNS:
            counts["total_permanent"][col] += counts[level_code][col]
            totals["total_permanent"][col] += totals[level_code][col]
    for col in DEMOGRAPHIC_COLUMNS:
        counts["grand_total"][col] = counts["total_permanent"][col] + counts["temporary_employees"][col]
        totals["grand_total"][col] = totals["total_permanent"][col] + totals["temporary_employees"][col]

    return {"number_of_employees": counts, "total_remuneration": totals}


def highest_and_lowest_paid_by_level(period_start, period_end, as_of_date) -> dict:
    """EEA4 Section D1/D2 — the single highest- and single lowest-paid
    employee's fixed/variable/total remuneration, per level x
    demographic column. D2 (lowest) is scoped to the lowest occupational
    level only, per the form's own note; D1 (highest) covers every level."""
    records = list(_remuneration_for_period(period_start, period_end))
    version_by_employee = {
        v.employee_id: v
        for v in EmployeeVersion.objects.as_at(as_of_date).select_related("occupational_level").filter(
            employee_id__in=[r.employee_id for r in records]
        )
    }

    highest = {row: {} for row in OCCUPATIONAL_LEVEL_CODES}
    lowest_level_code = OCCUPATIONAL_LEVEL_CODES[-1]
    lowest = {}

    by_level_col: dict[tuple[str, str], list] = {}
    for record in records:
        version = version_by_employee.get(record.employee_id)
        if version is None:
            continue
        level_code = version.occupational_level.code
        if level_code not in OCCUPATIONAL_LEVEL_CODES:
            continue
        col = demographic_column(version)
        if col is None:
            continue
        by_level_col.setdefault((level_code, col), []).append(record)

    for (level_code, col), recs in by_level_col.items():
        # tie-break: prefer higher variable remuneration for the highest,
        # lower variable remuneration for the lowest (EEA-Form-Spec-Notes.md).
        top = max(recs, key=lambda r: (r.total_remuneration, r.variable_remuneration))
        highest[level_code][col] = {
            "fixed": top.fixed_remuneration, "variable": top.variable_remuneration, "total": top.total_remuneration,
        }
        if level_code == lowest_level_code:
            bottom = min(recs, key=lambda r: (r.total_remuneration, -r.variable_remuneration))
            lowest[col] = {
                "fixed": bottom.fixed_remuneration, "variable": bottom.variable_remuneration,
                "total": bottom.total_remuneration,
            }

    return {"highest_paid": highest, "lowest_paid_lowest_level": lowest}


def median_and_gap_stats(period_start, period_end) -> dict:
    """EEA4 Section E — top-5%/bottom-5% headcount, range, median, and
    the vertical gap multiple."""
    totals = sorted(r.total_remuneration for r in _remuneration_for_period(period_start, period_end))
    n = len(totals)
    if n == 0:
        return {
            "employee_count": 0, "median_remuneration": None,
            "top_5_pct": {"count": 0, "total": 0, "range_low": None, "range_high": None},
            "bottom_5_pct": {"count": 0, "total": 0, "range_low": None, "range_high": None},
            "vertical_gap_multiple": None,
        }

    def _median(values):
        # Remuneration is whole Rand throughout (EEA-Form-Spec-Notes.md:
        # "no separators or decimals") -- an even-count average of two ints
        # can land on a X.5, so round back to a whole Rand rather than
        # leaking a float into a field the form spec requires as an integer.
        mid = len(values) // 2
        if len(values) % 2:
            return values[mid]
        return round((values[mid - 1] + values[mid]) / 2)

    five_pct = max(round(n * 0.05), 1) if n >= 1 else 0
    bottom_slice = totals[:five_pct]
    top_slice = totals[-five_pct:] if five_pct else []

    return {
        "employee_count": n,
        "median_remuneration": _median(totals),
        "top_5_pct": {
            "count": len(top_slice), "total": sum(top_slice),
            "range_low": top_slice[0] if top_slice else None, "range_high": top_slice[-1] if top_slice else None,
        },
        "bottom_5_pct": {
            "count": len(bottom_slice), "total": sum(bottom_slice),
            "range_low": bottom_slice[0] if bottom_slice else None, "range_high": bottom_slice[-1] if bottom_slice else None,
        },
        "vertical_gap_multiple": round(totals[-1] / totals[0], 1) if totals[0] else None,
    }
