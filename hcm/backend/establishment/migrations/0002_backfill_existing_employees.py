"""One-time backfill: one approved Position per currently-employed
EmployeeVersion, so approved-vs-filled/vacancy-rate is meaningful from day
one, not just for hires made after this feature ships. See
establishment/services.py::backfill_positions_for_current_employees for
the logic and why this uses real model imports rather than apps.get_model
historical state (docs/superpowers/plans/2026-08-19-position-establishment.md,
Task 5)."""
from django.db import migrations


def backfill(apps, schema_editor):
    from establishment.services import backfill_positions_for_current_employees

    backfill_positions_for_current_employees()


def noop_reverse(apps, schema_editor):
    # Deliberately not reversed: unlinking EmployeeVersion.position and
    # deleting the backfilled Position rows on a reverse migration would
    # destroy real establishment data a user may have built on top of by
    # then (later Positions referencing these, approval history, etc.).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("establishment", "0001_initial"),
        ("core_hr", "0006_employeeversion_position_and_more"),
    ]

    operations = [migrations.RunPython(backfill, noop_reverse)]
