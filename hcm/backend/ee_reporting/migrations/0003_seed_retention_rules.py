"""Seed explicit RETAIN retention rules for the EE plan and its evidence
trail (design spec 2026-08-26). EE Regulations 2025 reg. 9(15): the plan is
retained for five years after it expires; the forum records, measures and
progress snapshots are the evidence a s.43 DG review or a DEL inspection
asks for against that plan, so they carry the same rule. period_months=60
documents the statutory floor and has no runtime effect for a `retain` rule
(rbac_audit/retention.py skips RETAIN outright) -- same shape and posture
as core_hr/migrations/0011 and documents/migrations/0002: idempotent
get_or_create, entity_type as a bare string."""
from django.db import migrations

DEFAULTS = [
    ("ee_reporting.EEPlan", 60, "retain"),
    ("ee_reporting.EEPlanMeasure", 60, "retain"),
    ("ee_reporting.EEPlanProgressSnapshot", 60, "retain"),
    ("ee_reporting.EEForumMember", 60, "retain"),
    ("ee_reporting.EEForumMeeting", 60, "retain"),
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
        ("ee_reporting", "0002_eeplan_eap_profile_historicaleeplan_eap_profile_and_more"),
        ("rbac_audit", "0009_alter_consentrecord_purpose"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
