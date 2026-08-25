"""Seed RetentionRule rows for the new document/dependant/emergency-contact
entities (design spec §7). Same shape as
core_hr/migrations/0011_seed_employment_retention_rules.py: idempotent
get_or_create, entity_type as a bare string (no cross-app model import
needed for a RunPython seed).

documents.EmployeeDocument: RETAIN, 84 months documented (no runtime effect
for a `retain` rule) -- deliberately more conservative than
EmploymentEvent's 36 months, because employment contracts and qualification
evidence are the kind of record a CCMA dispute or SETA audit can reach back
further for than a plain termination-reason record.

core_hr.Dependant / core_hr.EmergencyContact: DELETE, 1 month -- unlike
documents, these have no standalone evidentiary value once detached from
an active employee relationship; a short window reflects that this is
genuinely disposable once stale. No handler is registered yet
(rbac_audit/retention.py's _HANDLERS) -- same "recorded decision, executor
is follow-up work" posture the pre-existing RetentionRule rows already
carry; a rule with no handler reports `no_handler` and changes nothing at
runtime."""
from django.db import migrations

DEFAULTS = [
    ("documents.EmployeeDocument", 84, "retain"),
    ("core_hr.Dependant", 1, "delete"),
    ("core_hr.EmergencyContact", 1, "delete"),
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
        ("documents", "0001_initial"),
        ("rbac_audit", "0009_alter_consentrecord_purpose"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
