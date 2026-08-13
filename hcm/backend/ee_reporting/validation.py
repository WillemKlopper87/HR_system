from __future__ import annotations

from .constants import DEMOGRAPHIC_COLUMNS
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
