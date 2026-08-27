"""Seed the RETAIN retention rule the C6 slice missed: EEReport, the
frozen EEA2/EEA4 snapshot table (form_type distinguishes the two forms on
one model -- Architecture-Design.md 5.1). EE Regulations 2025 reg. 10(14)
requires the EEA2 report to be kept five years after submission; reg.
12(3) sets the same five years for the EEA4 income-differential
statement -- both land on this one entity_type since a signed-off EEA4 is
just an EEReport row with form_type="eea4". 0003_seed_retention_rules.py
covered the plan and its evidence trail (reg. 9(15)) but not the report
itself. Same shape as that migration: period_months=60 documents the
statutory floor and has no runtime effect for a `retain` rule
(rbac_audit/retention.py skips RETAIN outright); idempotent get_or_create."""
from django.db import migrations

DEFAULTS = [
    ("ee_reporting.EEReport", 60, "retain"),
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
        ("ee_reporting", "0003_seed_retention_rules"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
