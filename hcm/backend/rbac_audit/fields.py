"""HCM remediation H-4: a Django model field that is transparently
encrypted at rest. A genuine `models.CharField` subclass (not a bare
Python property) so DRF's ModelSerializer, django-simple-history, the
admin, and every other piece of Django machinery that introspects model
fields keeps working exactly as it does for a plain CharField -- callers
read and write `instance.some_field` as a normal string; encryption and
decryption happen only at the DB boundary (get_prep_value/from_db_value).

`max_length` here governs the STORED ciphertext's column width, not the
plaintext's -- Fernet's authenticated-encryption overhead (version byte,
timestamp, IV, HMAC, base64) adds a fixed ~100 bytes to any plaintext, so
this field does not enforce a plaintext-length validator the way a plain
CharField(max_length=13) would. Add that validation at the serializer/
form layer if a field's true plaintext length still needs enforcing --
deliberately out of scope for this change (a data-quality concern, not a
security one)."""
from __future__ import annotations

from django.db import models

from .field_encryption import decrypt_value, encrypt_value


class EncryptedCharField(models.CharField):
    description = "A Restricted-tier value, encrypted at rest (HCM remediation H-4)."

    def __init__(self, *args, purpose: str, max_length: int = 500, **kwargs):
        self.purpose = purpose
        super().__init__(*args, max_length=max_length, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["purpose"] = self.purpose
        return name, path, args, kwargs

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        return encrypt_value(value, purpose=self.purpose)

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        return decrypt_value(value, purpose=self.purpose)
