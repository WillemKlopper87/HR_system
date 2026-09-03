"""HCM remediation H-4, phase 1: populate the *_encrypted mirror fields
(core_hr.Employee.national_id_number_encrypted/passport_number_encrypted,
rbac_audit.TOTPDevice.secret_encrypted) from their plaintext originals.

Bounded and resumable (spec H-4's migration-safety requirement): processes
in batches, skips rows that already have a non-empty encrypted value (so
an interrupted run picks back up rather than re-encrypting everything),
and reports progress as it goes.

    manage.py backfill_field_encryption            # backfill everything
    manage.py backfill_field_encryption --batch-size 200
    manage.py backfill_field_encryption --dry-run   # count only, write nothing
    manage.py backfill_field_encryption --verify    # decrypt every already-backfilled
                                                     # row and confirm it matches the
                                                     # plaintext original; writes nothing

Does not touch the plaintext columns and does not switch anything to read
from the encrypted fields -- that is phase 2, a deliberate follow-up once
this backfill has been run and verified against production data."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core_hr.models import Employee
from rbac_audit.field_encryption import FieldDecryptionError
from rbac_audit.models import TOTPDevice

# (model, plaintext attr, encrypted attr)
_TARGETS = [
    (Employee, "national_id_number", "national_id_number_encrypted"),
    (Employee, "passport_number", "passport_number_encrypted"),
    (TOTPDevice, "secret", "secret_encrypted"),
]


class Command(BaseCommand):
    help = "Backfill *_encrypted mirror fields from their plaintext originals (HCM remediation H-4, phase 1)."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--dry-run", action="store_true", help="Count only; write nothing.")
        parser.add_argument(
            "--verify", action="store_true",
            help="Decrypt every already-backfilled row and confirm it matches the plaintext original. Writes nothing.",
        )

    def handle(self, *args, **options):
        if options["verify"]:
            self._verify()
            return
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]
        for model, plain_attr, enc_attr in _TARGETS:
            self._backfill_one(model, plain_attr, enc_attr, batch_size=batch_size, dry_run=dry_run)

    def _backfill_one(self, model, plain_attr, enc_attr, *, batch_size, dry_run):
        pending = model.objects.exclude(**{plain_attr: ""}).filter(**{enc_attr: ""}).order_by("pk")
        total = pending.count()
        label = f"{model._meta.label}.{plain_attr}"
        if total == 0:
            self.stdout.write(f"{label}: nothing to backfill.")
            return
        if dry_run:
            self.stdout.write(f"{label}: {total} row(s) would be backfilled (dry run).")
            return

        done = 0
        while True:
            batch = list(pending[:batch_size])
            if not batch:
                break
            with transaction.atomic():
                for row in batch:
                    setattr(row, enc_attr, getattr(row, plain_attr))
                    row.save(update_fields=[enc_attr])
            done += len(batch)
            self.stdout.write(f"{label}: {done}/{total} backfilled...")
        self.stdout.write(self.style.SUCCESS(f"{label}: {done} row(s) backfilled."))

    def _verify(self):
        """Re-fetches each backfilled row fresh (a new queryset per row, not
        relying on any in-memory state from a prior save in this process),
        so `getattr(row, enc_attr)` genuinely exercises the DB round trip:
        stored ciphertext -> EncryptedCharField.from_db_value() ->
        decrypted plaintext -- and confirms it matches the original."""
        failures = 0
        checked = 0
        for model, plain_attr, enc_attr in _TARGETS:
            label = f"{model._meta.label}.{plain_attr}"
            for pk in model.objects.exclude(**{enc_attr: ""}).order_by("pk").values_list("pk", flat=True):
                checked += 1
                try:
                    # from_db_value() (the actual decryption) runs while this
                    # queryset is evaluated, not lazily on attribute access --
                    # a corrupted/undecryptable value raises right here.
                    row = model.objects.get(pk=pk)
                except FieldDecryptionError as exc:
                    self.stdout.write(self.style.ERROR(f"{label} pk={pk}: {exc}"))
                    failures += 1
                    continue
                if getattr(row, enc_attr) != getattr(row, plain_attr):
                    self.stdout.write(self.style.ERROR(f"{label} pk={pk}: decrypted value does not match plaintext."))
                    failures += 1
        if failures:
            raise CommandError(f"{failures}/{checked} backfilled row(s) failed verification.")
        self.stdout.write(self.style.SUCCESS(f"Verified {checked} backfilled row(s): all decrypt correctly and match."))
