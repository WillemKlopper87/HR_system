"""HCM remediation H-4, phase 2: cut TOTPDevice.secret over from the
plaintext column to the encrypted mirror added in 0012, then remove the
plaintext column. See core_hr/migrations/0024_h4_phase2_cutover.py's
docstring for why this is safe as one migration (no live production data
yet) and why a live cutover on real data must not follow this pattern."""
from django.db import migrations


def backfill_encrypted_mirror(apps, schema_editor):
    TOTPDevice = apps.get_model("rbac_audit", "TOTPDevice")
    for device in TOTPDevice.objects.all().iterator():
        if device.secret and not device.secret_encrypted:
            device.secret_encrypted = device.secret
            device.save(update_fields=["secret_encrypted"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("rbac_audit", "0012_totpdevice_secret_encrypted"),
    ]

    operations = [
        migrations.RunPython(backfill_encrypted_mirror, noop_reverse),
        migrations.RemoveField(model_name="totpdevice", name="secret"),
        migrations.RenameField(model_name="totpdevice", old_name="secret_encrypted", new_name="secret"),
    ]
