"""Default RetentionRule rows for the entity types that have a registered
retention handler (rbac_audit/retention.py, recruitment/retention.py).

Data-Dictionary.md: audit log retention >= 5 years (seeded as RETAIN — an
hr_admin/sysadmin must consciously switch it to delete-after-N-months);
step-up grants are 15-minute ephemera (purge after a month); "unsuccessful
applicants -> anonymise after 12 months" is the dictionary's own example.
Idempotent: existing rows for these entity types are left untouched.
"""
from django.db import migrations

DEFAULTS = [
    ("rbac_audit.AuditLogEntry", 60, "retain"),
    ("rbac_audit.StepUpGrant", 1, "delete"),
    ("recruitment.Applicant", 12, "anonymise"),
]


def seed(apps, schema_editor):
    RetentionRule = apps.get_model("rbac_audit", "RetentionRule")
    for entity_type, months, action in DEFAULTS:
        RetentionRule.objects.get_or_create(
            entity_type=entity_type, defaults={"period_months": months, "action": action, "active": True}
        )


def unseed(apps, schema_editor):
    RetentionRule = apps.get_model("rbac_audit", "RetentionRule")
    RetentionRule.objects.filter(entity_type__in=[e for e, _, _ in DEFAULTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rbac_audit", "0006_alter_auditlogentry_action_totpdevice_stepupgrant"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
