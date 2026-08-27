"""Seed all 18 EEA17 economic sectors with the 5-year sectoral numerical
targets gazetted under EEA s.15A(2) — Determination of Sectoral Numerical
Targets, GN 6124, Government Gazette 52514, 15 April 2025 ("5-Year
Sectoral Numerical Targets for All Sectors" table, pp.6-10). Transcribed
verbatim from the gazette PDF (gov.za, downloaded and read directly, per
the field-guide caveat that scorecard/reporting-window figures should
come from the gazette text, not commentary). Every sector carries the
same 3% disability target (the gazette states this per sector; it is not
sector-varying). Percentages are the workforce shares the gazette
publishes (male/female/total per level, not a gap to close), matching
the shape EEPlan.sector_targets already uses (see
0003_seed_retention_rules.py's neighbour, test_forum_plan.py's fixture)."""
from decimal import Decimal

from django.db import migrations

DISABILITY_TARGET = Decimal("3.00")

SECTORS = [
    ("1.1", "Accommodation and Food Service Activities", {
        "TOP": {"male": 18.6, "female": 38.1, "total": 56.7},
        "SENIOR": {"male": 32.2, "female": 46.1, "total": 78.3},
        "PQ": {"male": 38.6, "female": 46.1, "total": 84.7},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.2", "Administrative and Support Activities", {
        "TOP": {"male": 33.2, "female": 36.7, "total": 69.9},
        "SENIOR": {"male": 42.3, "female": 43.5, "total": 85.8},
        "PQ": {"male": 49.2, "female": 46.1, "total": 95.3},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.3", "Agriculture, Forestry & Fishing", {
        "TOP": {"male": 13.2, "female": 20.8, "total": 34.0},
        "SENIOR": {"male": 21.6, "female": 31.0, "total": 52.6},
        "PQ": {"male": 34.7, "female": 41.7, "total": 76.4},
        "SKILLED": {"male": 49.8, "female": 44.0, "total": 93.8},
    }),
    ("1.4", "Arts, Entertainment and Recreation", {
        "TOP": {"male": 35.1, "female": 33.5, "total": 68.6},
        "SENIOR": {"male": 40.3, "female": 43.8, "total": 84.1},
        "PQ": {"male": 49.8, "female": 46.1, "total": 95.9},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.5", "Construction", {
        "TOP": {"male": 30.0, "female": 24.8, "total": 54.8},
        "SENIOR": {"male": 38.3, "female": 27.8, "total": 66.1},
        "PQ": {"male": 46.7, "female": 34.4, "total": 81.1},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.6", "Education", {
        "TOP": {"male": 27.6, "female": 46.1, "total": 73.7},
        "SENIOR": {"male": 30.5, "female": 46.1, "total": 76.6},
        "PQ": {"male": 43.0, "female": 46.1, "total": 89.1},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.7", "Electricity, Gas, Steam and Air Conditioning Supply", {
        "TOP": {"male": 31.7, "female": 27.9, "total": 59.6},
        "SENIOR": {"male": 42.7, "female": 39.5, "total": 82.2},
        "PQ": {"male": 49.8, "female": 46.1, "total": 95.9},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.8", "Financial and Insurance Activities", {
        "TOP": {"male": 27.8, "female": 35.3, "total": 63.1},
        "SENIOR": {"male": 31.7, "female": 45.3, "total": 77.0},
        "PQ": {"male": 40.7, "female": 46.1, "total": 86.8},
        "SKILLED": {"male": 49.5, "female": 46.1, "total": 95.6},
    }),
    ("1.9", "Human Health and Social Work Activities", {
        "TOP": {"male": 27.6, "female": 43.7, "total": 71.3},
        "SENIOR": {"male": 39.8, "female": 46.1, "total": 85.9},
        "PQ": {"male": 49.8, "female": 46.1, "total": 95.9},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.10", "Information and Communication", {
        "TOP": {"male": 25.4, "female": 31.2, "total": 56.6},
        "SENIOR": {"male": 28.6, "female": 40.0, "total": 68.6},
        "PQ": {"male": 37.9, "female": 38.9, "total": 76.8},
        "SKILLED": {"male": 46.0, "female": 45.7, "total": 91.7},
    }),
    ("1.11", "Manufacturing", {
        "TOP": {"male": 24.1, "female": 25.0, "total": 49.1},
        "SENIOR": {"male": 32.4, "female": 33.6, "total": 66.0},
        "PQ": {"male": 40.4, "female": 37.7, "total": 78.1},
        "SKILLED": {"male": 49.8, "female": 39.6, "total": 89.4},
    }),
    ("1.12", "Mining and Quarrying", {
        "TOP": {"male": 33.1, "female": 24.4, "total": 57.5},
        "SENIOR": {"male": 36.3, "female": 28.2, "total": 64.5},
        "PQ": {"male": 43.2, "female": 34.4, "total": 77.6},
        "SKILLED": {"male": 49.8, "female": 36.9, "total": 86.7},
    }),
    ("1.13", "Professional, Scientific and Technical Activities", {
        "TOP": {"male": 24.4, "female": 38.1, "total": 62.5},
        "SENIOR": {"male": 29.9, "female": 46.1, "total": 76.0},
        "PQ": {"male": 35.9, "female": 46.1, "total": 82.0},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.14", "Public Administration and Defence; Compulsory Social Security", {
        "TOP": {"male": 49.8, "female": 41.9, "total": 91.7},
        "SENIOR": {"male": 49.8, "female": 46.1, "total": 95.9},
        "PQ": {"male": 49.8, "female": 46.1, "total": 95.9},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.15", "Real Estate Activities", {
        "TOP": {"male": 18.9, "female": 30.3, "total": 49.2},
        "SENIOR": {"male": 22.9, "female": 46.1, "total": 69.0},
        "PQ": {"male": 32.4, "female": 46.1, "total": 78.5},
        "SKILLED": {"male": 38.3, "female": 46.1, "total": 84.4},
    }),
    ("1.16", "Transportation and Storage", {
        "TOP": {"male": 32.2, "female": 30.0, "total": 62.2},
        "SENIOR": {"male": 42.1, "female": 35.9, "total": 78.0},
        "PQ": {"male": 46.3, "female": 40.7, "total": 87.0},
        "SKILLED": {"male": 49.8, "female": 41.4, "total": 91.2},
    }),
    ("1.17", "Water Supply, Sewerage, Waste Management and Remediation Activities", {
        "TOP": {"male": 49.8, "female": 35.9, "total": 85.7},
        "SENIOR": {"male": 49.8, "female": 41.0, "total": 90.8},
        "PQ": {"male": 49.8, "female": 46.1, "total": 95.9},
        "SKILLED": {"male": 49.8, "female": 46.1, "total": 95.9},
    }),
    ("1.18", "Wholesale and Retail Trade; Repair of Motor Vehicles and Motorcycles", {
        "TOP": {"male": 24.2, "female": 27.5, "total": 51.7},
        "SENIOR": {"male": 35.0, "female": 38.6, "total": 73.6},
        "PQ": {"male": 42.2, "female": 46.1, "total": 88.3},
        "SKILLED": {"male": 48.1, "female": 46.1, "total": 94.2},
    }),
]


def seed(apps, schema_editor):
    EESector = apps.get_model("ee_reporting", "EESector")
    for code, name, targets in SECTORS:
        EESector.objects.get_or_create(
            code=code, defaults={"name": name, "targets": targets, "disability_target_pct": DISABILITY_TARGET}
        )


def unseed(apps, schema_editor):
    EESector = apps.get_model("ee_reporting", "EESector")
    EESector.objects.filter(code__in=[c for c, _, _ in SECTORS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ee_reporting", "0005_add_ee_sector"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
