from django.db import migrations

# EEA-Form-Spec-Notes.md: "Sign-off: Accounting Officer (PFMA employer) —
# the approval chain for generated reports must end at CEO/Accounting
# Officer, not just the EE manager." No such role existed in the original
# eight-role matrix (Sprint 2) — ee_manager's own description already
# anticipated a "sign-off chain" but not who signs at the end of it.
# Minimal generic tier grants (mirrors sysadmin's reasoning): this role's
# entire job is the ee_reporting module's dedicated sign-off action,
# gated by an explicit permission check there, not the generic P/I/S/R
# system — see ee_reporting/permissions.py.
ROLE = {
    "name": "accounting_officer",
    "display_name": "Accounting Officer / CEO",
    "row_scope": "all",
    "description": (
        "Final EEA2/EEA4 sign-off (PFMA employer — EEA-Form-Spec-Notes.md). "
        "No standing access to S/R business data outside the ee_reporting "
        "approval action itself."
    ),
    "grants": {"P": (False, False), "I": (False, False), "S": (False, False), "R": (False, False)},
}


def seed_role(apps, schema_editor):
    Role = apps.get_model("rbac_audit", "Role")
    RoleFieldTierGrant = apps.get_model("rbac_audit", "RoleFieldTierGrant")
    role, _ = Role.objects.update_or_create(
        name=ROLE["name"],
        defaults={
            "display_name": ROLE["display_name"],
            "description": ROLE["description"],
            "row_scope": ROLE["row_scope"],
            "active": True,
        },
    )
    for tier, (can_read, can_write) in ROLE["grants"].items():
        RoleFieldTierGrant.objects.update_or_create(
            role=role, tier=tier, defaults={"can_read": can_read, "can_write": can_write}
        )


def remove_role(apps, schema_editor):
    Role = apps.get_model("rbac_audit", "Role")
    Role.objects.filter(name=ROLE["name"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac_audit", "0004_alter_consentrecord_purpose"),
    ]

    operations = [
        migrations.RunPython(seed_role, remove_role),
    ]
