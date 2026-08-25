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
        "position": FieldTier.PUBLIC,
        "contract_end_date": FieldTier.PUBLIC,
        # ContractRenewalDecisionSerializer is a plain ModelSerializer, not
        # a TieredModelSerializer, so per-field tiering never applies
        # inside it (core_hr.ContractRenewalDecision's own
        # recommended_comment/decided_comment INTERNAL entries below are
        # otherwise dead for reads through this endpoint) -- gating the
        # OUTER contract_renewal_decision field here is what actually
        # controls read access to the whole nested object. INTERNAL was
        # chosen, not a stricter tier, because every intended consumer
        # (line_manager, hr_admin, auditor -- design spec §6) holds
        # I:read=True in the seeded role matrix (0002_seed_roles.py), while
        # sysadmin (I:read=False, "no standing access to S/R business
        # data") does not -- exactly the exposure this closes.
        "contract_renewal_decision": FieldTier.INTERNAL,
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
    "core_hr.ContractRenewalDecision": {
        "recommended_comment": FieldTier.INTERNAL,
        "decided_comment": FieldTier.INTERNAL,
    },
    # C2 (docs/superpowers/specs/2026-08-25-employee-documents-popia-design.md
    # §2.9): personal data about a third party who holds no seat at this
    # system's RBAC table -- Sensitive by default (stricter than the
    # employee's own analogous fields), Restricted for a third-party ID
    # number, matching Employee.national_id_number's own tier.
    "core_hr.Dependant": {
        "first_name": FieldTier.SENSITIVE,
        "last_name": FieldTier.SENSITIVE,
        "relationship": FieldTier.SENSITIVE,
        "date_of_birth": FieldTier.SENSITIVE,
        "id_number": FieldTier.RESTRICTED,
        "notes": FieldTier.SENSITIVE,
    },
    "core_hr.EmergencyContact": {
        "name": FieldTier.SENSITIVE,
        "relationship": FieldTier.SENSITIVE,
        "phone": FieldTier.SENSITIVE,
        "alternative_phone": FieldTier.SENSITIVE,
        "email": FieldTier.SENSITIVE,
    },
    "recruitment.Applicant": {
        "first_name": FieldTier.PUBLIC,
        "last_name": FieldTier.PUBLIC,
        "email": FieldTier.INTERNAL,
        "phone": FieldTier.INTERNAL,
        "date_of_birth": FieldTier.SENSITIVE,
        "current_stage": FieldTier.PUBLIC,
        "rejected_reason": FieldTier.INTERNAL,
        # Consent-gated on top of this tier grant, not instead of it — see
        # recruitment/serializers.py::ApplicantSerializer.
        "race": FieldTier.SENSITIVE,
        "gender": FieldTier.SENSITIVE,
        "disability_status": FieldTier.SENSITIVE,
    },
    "performance.Goal": {
        "title": FieldTier.INTERNAL,
        "description": FieldTier.INTERNAL,
        "target_date": FieldTier.INTERNAL,
        "status": FieldTier.INTERNAL,
    },
    # performance.Review and performance.Feedback are Sensitive-tier
    # (Data-Dictionary.md: "review (S — ratings), feedback (S)") but
    # deliberately NOT registered here — line_manager's generic S-tier
    # grant is closed (aggregate-only, for demographics) yet RBAC-Roles.md
    # says line_manager individually "sees own team's reviews/goals".
    # performance/views.py gates these by row-scope alone (RowScopePermission —
    # there is no performance/permissions.py), the same exception pattern as
    # recruitment.Offer's pay fields.
    "learning.EmployeeSkill": {
        "proficiency": FieldTier.INTERNAL,
        "acquired_date": FieldTier.INTERNAL,
        "notes": FieldTier.INTERNAL,
    },
    "learning.Certification": {
        "name": FieldTier.INTERNAL,
        "issuing_body": FieldTier.INTERNAL,
        "credential_id": FieldTier.INTERNAL,
        "issue_date": FieldTier.INTERNAL,
        "expiry_date": FieldTier.INTERNAL,
    },
    "learning.TrainingRecord": {
        "title": FieldTier.INTERNAL,
        "provider": FieldTier.INTERNAL,
        "status": FieldTier.INTERNAL,
        "start_date": FieldTier.INTERNAL,
        "completion_date": FieldTier.INTERNAL,
        "hours": FieldTier.INTERNAL,
        "cost": FieldTier.INTERNAL,
    },
}


def tier_of(model_label: str, field_name: str) -> str:
    return FIELD_TIERS.get(model_label, {}).get(field_name, FieldTier.PUBLIC)


def highest_tier(model_label: str, field_names) -> str:
    tiers = [tier_of(model_label, f) for f in field_names]
    if not tiers:
        return FieldTier.PUBLIC
    return max(tiers, key=lambda t: TIER_ORDER[t])
