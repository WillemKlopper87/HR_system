from __future__ import annotations

# Verbatim from EEA2 Form.docx / EEA4 Form.docx (see EEA-Form-Spec-Notes.md
# for how these were extracted and cross-checked). Keeping these as one
# shared module — not duplicated across models/aggregation/export — is
# what makes "form layouts are versioned configuration, not code" (gap C3,
# Architecture-Design.md §11) actually true: a real annual DEL wording
# change is a one-file edit here.

# Matches core_hr's seeded OccupationalLevel codes exactly (EEA9) —
# core_hr/migrations/0002_seed_occupational_levels.py.
OCCUPATIONAL_LEVEL_CODES = ["TOP", "SENIOR", "PQ", "SKILLED", "SEMI", "UNSKILLED"]

# The 10 demographic columns every EEA2/EEA4 workforce matrix uses:
# African/Coloured/Indian/White x Male/Female (citizens only), plus
# Foreign National Male/Female (not raced) — EEA-Form-Spec-Notes.md
# "Population groups" / "Foreign Nationals are separate ... not raced".
DEMOGRAPHIC_COLUMNS = [
    "african_male", "coloured_male", "indian_male", "white_male",
    "african_female", "coloured_female", "indian_female", "white_female",
    "foreign_national_male", "foreign_national_female",
]
# Section D (Skills Development) has no Foreign National columns on the
# form — 8 columns, not 10.
SKILLS_DEMOGRAPHIC_COLUMNS = DEMOGRAPHIC_COLUMNS[:8]

AGGREGATE_ROW_KEYS = ["total_permanent", "temporary_employees", "grand_total"]

# EEA2 Section B: "Justifiable reasons for not meeting EE Sector Targets"
# — 7 fixed categories, one grid row per occupational level + disability.
JUSTIFIABLE_REASONS = [
    ("insufficient_recruitment_opportunities", "Insufficient recruitment opportunities"),
    ("insufficient_promotion_opportunities", "Insufficient promotion opportunities"),
    (
        "insufficient_target_individuals",
        "Insufficient target individuals with relevant qualification, prior learning, "
        "experience or capacity to acquire ability to do job",
    ),
    ("ccma_award_court_order", "CCMA Award/Court Order"),
    ("transfer_of_business", "Transfer of business"),
    ("mergers_acquisitions", "Mergers/Acquisitions"),
    ("economic_conditions", "Impact of Economic Conditions on Business"),
]
JUSTIFIABLE_REASON_ROW_KEYS = OCCUPATIONAL_LEVEL_CODES + ["disability"]

# EEA2 Section F: consultation stakeholders — 3 fixed items.
CONSULTATION_STAKEHOLDERS = [
    ("consultative_body_or_ee_forum", "Consultative body or employment equity forum"),
    ("representative_trade_unions", "Representative trade union(s)"),
    ("employees", "Employees"),
]

# EEA2 Section F: barriers & affirmative action measures — 24 fixed
# categories, each with barriers Y/N, AA measures Y/N, start/end date.
BARRIER_CATEGORIES = [
    ("recruitment", "Recruitment"),
    ("advertisement_of_positions", "Advertisement of positions"),
    ("selection_criteria", "Selection criteria"),
    ("appointments", "Appointments"),
    ("job_classification_and_grading", "Job classification and grading"),
    ("remuneration_and_benefits", "Remuneration and benefits"),
    ("terms_and_conditions_of_employment", "Terms & conditions of employment"),
    ("job_assignments", "Job assignments"),
    ("work_environment_and_facilities", "Work environment and facilities"),
    ("training_and_development", "Training and development"),
    ("performance_and_evaluation", "Performance and evaluation"),
    ("promotions", "Promotions"),
    ("transfers", "Transfers"),
    ("succession_and_experience_planning", "Succession & experience planning"),
    ("disciplinary_measures", "Disciplinary measures"),
    ("dismissals", "Dismissals"),
    ("retention_of_designated_groups", "Retention of designated groups"),
    ("corporate_culture", "Corporate culture"),
    ("reasonable_accommodation", "Reasonable accommodation"),
    ("harassment", "Harassment"),
    ("hiv_aids_prevention_and_wellness", "HIV&AIDS prevention and wellness programmes"),
    ("assigned_senior_managers", "Assigned senior manager(s) to manage EE implementation"),
    ("budget_allocation", "Budget allocation in support of employment equity goals"),
    ("time_off_for_ee_committee", "Time off for employment equity consultative committee to meet"),
]
assert len(BARRIER_CATEGORIES) == 24

# EEA4 Section E: key reason for income differentials — 8 fixed options.
DIFFERENTIAL_REASONS = [
    ("seniority_length_of_service", "Seniority/length of service"),
    ("qualifications", "Qualifications"),
    ("performance", "Performance"),
    ("demotion", "Demotion"),
    ("experiential_training", "Experiential training"),
    ("shortage_of_skill", "Shortage of skill"),
    ("transfer_of_business", "Transfer of business"),
    ("other", "Other"),
]

BUSINESS_TYPES = [
    ("private_sector", "Private Sector"),
    ("national_government", "National Government"),
    ("local_government", "Local Government"),
    ("non_profit_organisation", "Non-profit Organisation"),
    ("state_owned_enterprise", "State Owned Enterprise"),
    ("provincial_government_educational_institution", "Provincial Government Educational Institution"),
]

EMPLOYEE_COUNT_BANDS = [
    ("1_to_49", "1 to 49"),
    ("50_to_149", "50 to 149"),
    ("150_or_more", "150 or more"),
]

MONITORING_FREQUENCIES = [
    ("monthly", "Monthly"),
    ("quarterly", "Quarterly"),
    ("biannually", "Bi-annually"),
    ("annually", "Annually"),
]


def empty_matrix(row_keys=None, column_keys=None) -> dict:
    row_keys = row_keys or (OCCUPATIONAL_LEVEL_CODES + AGGREGATE_ROW_KEYS)
    column_keys = column_keys or DEMOGRAPHIC_COLUMNS
    return {row: dict.fromkeys(column_keys, 0) for row in row_keys}
