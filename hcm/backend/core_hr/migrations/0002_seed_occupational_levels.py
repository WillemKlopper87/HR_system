from django.db import migrations

# The six statutory EEA occupational levels (EEA9), confirmed from the
# received EEA2/EEA4 forms — see HR_system/EEA-Form-Spec-Notes.md.
OCCUPATIONAL_LEVELS = [
    ("TOP", "Top management", 1),
    ("SENIOR", "Senior management", 2),
    ("PQ", "Professionally qualified and experienced specialists and mid-management", 3),
    ("SKILLED", "Skilled technical, academically qualified and junior management", 4),
    ("SEMI", "Semi-skilled and discretionary decision making", 5),
    ("UNSKILLED", "Unskilled and defined decision making", 6),
]


def seed_occupational_levels(apps, schema_editor):
    OccupationalLevel = apps.get_model("core_hr", "OccupationalLevel")
    for code, name, order in OCCUPATIONAL_LEVELS:
        OccupationalLevel.objects.update_or_create(
            code=code, defaults={"name": name, "order": order, "active": True}
        )


def remove_occupational_levels(apps, schema_editor):
    OccupationalLevel = apps.get_model("core_hr", "OccupationalLevel")
    OccupationalLevel.objects.filter(code__in=[c for c, _, _ in OCCUPATIONAL_LEVELS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core_hr", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_occupational_levels, remove_occupational_levels),
    ]
