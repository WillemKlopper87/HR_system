"""HCM remediation H-4, phase 2: cut over Employee.national_id_number/
passport_number from the plaintext columns to the encrypted mirrors added
in 0023, then remove the plaintext columns.

Safe to do as one migration ONLY because this deployment has no live
production data yet (confirmed with the user before writing this) --
HCM_REMEDIATION_EXECUTION_PROTOCOL_2026-09-03.md's migration-safety
section requires a live cutover to be a separate, deliberate step after
an operator has run core_hr.backfill_field_encryption and verified it
against production data; skipping straight to this on a database with
real employee records would make every unbackfilled row's restricted
fields read as blank the moment this migration applied.

Uses apps.get_model() (historical model state), not a live import --
unlike establishment.0002_backfill_existing_employees (see
establishment/services.py's fix earlier in this remediation), this
backfill is scoped to exactly the two fields this migration's own state
declares, so it isn't exposed to whatever fields Employee gains later."""
from django.db import migrations


def backfill_encrypted_mirrors(apps, schema_editor):
    Employee = apps.get_model("core_hr", "Employee")
    for employee in Employee.objects.all().iterator():
        update_fields = []
        if employee.national_id_number and not employee.national_id_number_encrypted:
            employee.national_id_number_encrypted = employee.national_id_number
            update_fields.append("national_id_number_encrypted")
        if employee.passport_number and not employee.passport_number_encrypted:
            employee.passport_number_encrypted = employee.passport_number
            update_fields.append("passport_number_encrypted")
        if update_fields:
            employee.save(update_fields=update_fields)


def noop_reverse(apps, schema_editor):
    # Deliberately not reversed -- see spec §6.3-style non-destructive
    # philosophy elsewhere in this codebase; a reverse migration is not
    # how a rollback of a live cutover should happen.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("core_hr", "0023_employee_national_id_number_encrypted_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_encrypted_mirrors, noop_reverse),
        migrations.RemoveField(model_name="employee", name="national_id_number"),
        migrations.RemoveField(model_name="employee", name="passport_number"),
        migrations.RemoveField(model_name="historicalemployee", name="national_id_number"),
        migrations.RemoveField(model_name="historicalemployee", name="passport_number"),
        migrations.RenameField(model_name="employee", old_name="national_id_number_encrypted", new_name="national_id_number"),
        migrations.RenameField(model_name="employee", old_name="passport_number_encrypted", new_name="passport_number"),
        migrations.RenameField(model_name="historicalemployee", old_name="national_id_number_encrypted", new_name="national_id_number"),
        migrations.RenameField(model_name="historicalemployee", old_name="passport_number_encrypted", new_name="passport_number"),
    ]
