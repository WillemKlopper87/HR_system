from django.db import migrations

# The eight roles and their P/I/S/R (read, write) grants — RBAC-Roles.md.
# S-tier "consent-gated" and R-tier "band-scoped" nuances noted for
# recruiter are enforced at the recruitment-module level (Sprint 4), not
# by this generic grant — the generic layer only knows blanket tier access.
ROLE_MATRIX = [
    {
        "name": "employee",
        "display_name": "Employee",
        "row_scope": "self",
        "description": "Default role for every employee — own profile, consent, reviews.",
        "grants": {"P": (True, True), "I": (True, False), "S": (True, False), "R": (True, False)},
    },
    {
        "name": "line_manager",
        "display_name": "Line Manager",
        "row_scope": "own_team",
        "description": "Team views; demographics only as suppressed aggregates (Sprint 3) — no individual-level Sensitive read.",
        "grants": {"P": (True, False), "I": (True, False), "S": (False, False), "R": (False, False)},
    },
    {
        "name": "hr_admin",
        "display_name": "HR Admin",
        "row_scope": "all",
        "description": "Core HR data management, imports, data-quality queue.",
        "grants": {"P": (True, True), "I": (True, True), "S": (True, True), "R": (True, False)},
    },
    {
        "name": "ee_manager",
        "display_name": "EE Manager",
        "row_scope": "all",
        "description": "EE reporting, self-ID campaign, EEA sign-off chain. No pay access.",
        "grants": {"P": (True, False), "I": (True, False), "S": (True, True), "R": (False, False)},
    },
    {
        "name": "recruiter",
        "display_name": "Recruiter",
        "row_scope": "all",
        "description": (
            "Requisition-to-hire pipeline. S-tier applicant demographics are consent-gated "
            "at the recruitment-module level (Sprint 4); no blanket R-tier — offer amounts "
            "get a narrow band-scoped exception there."
        ),
        "grants": {"P": (True, True), "I": (True, True), "S": (True, False), "R": (False, False)},
    },
    {
        "name": "comp_manager",
        "display_name": "Compensation Manager",
        "row_scope": "all",
        "description": "Pay bands, comp review workflow, benefits config. Individual Sensitive-tier data only via aggregates.",
        "grants": {"P": (True, False), "I": (True, False), "S": (False, False), "R": (True, True)},
    },
    {
        "name": "auditor",
        "display_name": "Auditor",
        "row_scope": "all",
        "description": "Read-only everywhere, including the audit log itself — every auditor read is itself audited.",
        "grants": {"P": (True, False), "I": (True, False), "S": (True, False), "R": (True, False)},
    },
    {
        "name": "sysadmin",
        "display_name": "System Administrator",
        "row_scope": "all",
        "description": "Technical operations only. No standing access to S/R business data.",
        "grants": {"P": (False, False), "I": (False, False), "S": (False, False), "R": (False, False)},
    },
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("rbac_audit", "Role")
    RoleFieldTierGrant = apps.get_model("rbac_audit", "RoleFieldTierGrant")
    for entry in ROLE_MATRIX:
        role, _ = Role.objects.update_or_create(
            name=entry["name"],
            defaults={
                "display_name": entry["display_name"],
                "description": entry["description"],
                "row_scope": entry["row_scope"],
                "active": True,
            },
        )
        for tier, (can_read, can_write) in entry["grants"].items():
            RoleFieldTierGrant.objects.update_or_create(
                role=role, tier=tier, defaults={"can_read": can_read, "can_write": can_write}
            )


def remove_roles(apps, schema_editor):
    Role = apps.get_model("rbac_audit", "Role")
    Role.objects.filter(name__in=[entry["name"] for entry in ROLE_MATRIX]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac_audit", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, remove_roles),
    ]
