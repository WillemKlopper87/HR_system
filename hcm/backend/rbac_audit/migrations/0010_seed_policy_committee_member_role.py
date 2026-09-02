from django.db import migrations

# policies/services.py::publish_policy now requires every current holder of
# this role to have approved a draft before it can publish (Wireframe
# follow-up 2026-09-02: policy review needs a committee sign-off, not a
# single HR admin's own Publish click). Minimal generic tier grants, same
# reasoning as accounting_officer (0005) -- this role's whole job is the
# policies module's dedicated approval action, gated by an explicit
# has_role() check there, not the generic P/I/S/R system.
ROLE = {
    "name": "policy_committee_member",
    "display_name": "Policy Review Committee Member",
    "row_scope": "all",
    "description": (
        "Reviews and approves HR policy drafts before publication. Every current holder of this "
        "role must approve a draft before it can be published (policies/services.py). No standing "
        "access to S/R business data outside the policies module's own approval action."
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
        ("rbac_audit", "0009_alter_consentrecord_purpose"),
    ]

    operations = [
        migrations.RunPython(seed_role, remove_role),
    ]
