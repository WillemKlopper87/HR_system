"""One-time backfill: links each historical CLOSED/FILLED requisition to
the Position its resulting hire was backfilled into by
establishment.0002_backfill_existing_employees, which MUST run first (see
the dependency below). See recruitment/services.py::
backfill_requisition_positions and docs/superpowers/plans/
2026-08-19-position-establishment.md Task 8."""
from django.db import migrations


def backfill(apps, schema_editor):
    from recruitment.services import backfill_requisition_positions

    backfill_requisition_positions()


def noop_reverse(apps, schema_editor):
    pass  # same reasoning as establishment.0002 -- don't destroy real linkage on a reverse


class Migration(migrations.Migration):
    dependencies = [
        ("recruitment", "0003_requisition_positions"),  # the M2M-adding migration from Task 6 Step 6
        ("establishment", "0002_backfill_existing_employees"),
    ]

    operations = [migrations.RunPython(backfill, noop_reverse)]
