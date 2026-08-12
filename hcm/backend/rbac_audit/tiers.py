from __future__ import annotations

from django.db import models


class FieldTier(models.TextChoices):
    """Data-Dictionary.md sensitivity tiers. Every module registers its
    tiered models' fields in FIELD_TIERS below — this is the shared
    per-field sensitivity map the sprint plan requires every module to
    reuse rather than building its own access control."""

    PUBLIC = "P", "Public"
    INTERNAL = "I", "Internal"
    SENSITIVE = "S", "Sensitive"
    RESTRICTED = "R", "Restricted"


TIER_ORDER = {
    FieldTier.PUBLIC: 0,
    FieldTier.INTERNAL: 1,
    FieldTier.SENSITIVE: 2,
    FieldTier.RESTRICTED: 3,
}

FIELD_TIERS: dict[str, dict[str, str]] = {
    "core_hr.Employee": {
        "employee_number": FieldTier.PUBLIC,
        "first_name": FieldTier.PUBLIC,
        "last_name": FieldTier.PUBLIC,
        "preferred_name": FieldTier.PUBLIC,
        "national_id_number": FieldTier.RESTRICTED,
        "passport_number": FieldTier.RESTRICTED,
        "date_of_birth": FieldTier.SENSITIVE,
        "work_email": FieldTier.PUBLIC,
        "personal_email": FieldTier.INTERNAL,
        "phone": FieldTier.INTERNAL,
        "hire_date": FieldTier.INTERNAL,
    },
    "core_hr.EmployeeVersion": {
        "department": FieldTier.PUBLIC,
        "job_title": FieldTier.PUBLIC,
        "occupational_level": FieldTier.INTERNAL,
        "job_grade": FieldTier.INTERNAL,
        "manager": FieldTier.INTERNAL,
        "employment_status": FieldTier.INTERNAL,
        "citizenship_status": FieldTier.SENSITIVE,
        "location": FieldTier.INTERNAL,
        "race": FieldTier.SENSITIVE,
        "gender": FieldTier.SENSITIVE,
        "disability_status": FieldTier.SENSITIVE,
        "disability_detail": FieldTier.SENSITIVE,
        "race_source": FieldTier.SENSITIVE,
        "disability_source": FieldTier.SENSITIVE,
    },
}


def tier_of(model_label: str, field_name: str) -> str:
    return FIELD_TIERS.get(model_label, {}).get(field_name, FieldTier.PUBLIC)


def highest_tier(model_label: str, field_names) -> str:
    tiers = [tier_of(model_label, f) for f in field_names]
    if not tiers:
        return FieldTier.PUBLIC
    return max(tiers, key=lambda t: TIER_ORDER[t])
