"""Seed explicit RETAIN retention rules for the two employment-exit
entities central to C1 part 3 (design spec §7): EmploymentEvent (the EEA2
workforce-movement record) and EmploymentChange (the proposer/confirmer/
reason provenance a contested dismissal turns on). Neither entity has any
rule today, and rbac_audit's retention executor honours only what a rule
tells it to (a RETAIN rule is skipped outright, same as no rule at all) --
so this doesn't change runtime behaviour, it turns "nobody has proposed
anonymising or deleting these" into a recorded decision a future migration
would have to consciously override, per spec §7's own reasoning.

period_months=36 documents BCEA's 3-year-post-termination retention floor
(the number named in spec §7); it has no runtime effect for a `retain`
rule. Mirrors rbac_audit/migrations/0007_seed_default_retention_rules.py's
shape (idempotent get_or_create, entity_type as a bare string -- no import
of core_hr's models needed there, and none of rbac_audit's needed here)."""
from django.db import migrations

DEFAULTS = [
    ("core_hr.EmploymentEvent", 36, "retain"),
    ("core_hr.EmploymentChange", 36, "retain"),
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
        ("core_hr", "0010_employmentchange_historicalemploymentchange_and_more"),
        ("rbac_audit", "0007_seed_default_retention_rules"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
