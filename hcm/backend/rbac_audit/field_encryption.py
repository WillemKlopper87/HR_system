"""HCM remediation H-4: application-layer envelope encryption for
Restricted identity fields (core_hr.Employee.national_id_number/
passport_number) and TOTP seeds (TOTPDevice.secret). Disk/volume
encryption (ADR-005) protects against physical media loss but not against
a database dump, a read-only credential compromise, or an exposed backup
-- all of which still hand over a plaintext column directly. This module
is the crypto primitive; rbac_audit/fields.py's EncryptedCharField is
what model fields actually use.

Design::

    plaintext -> purpose-derived key (HKDF-SHA256 from FIELD_ENCRYPTION_KEYS)
              -> Fernet (AES-128-CBC + HMAC-SHA256, authenticated, versioned)
              -> ciphertext stored in the DB column (base64 text)

Purpose separation: every field encrypts under a DIFFERENT derived key
(HKDF with the purpose string as `info`), so a compromise of one field's
effective key does not expose another's -- decrypting "totp_seed"
ciphertext with the "national_id" subkey fails outright rather than
silently succeeding with garbage.

Key rotation: FIELD_ENCRYPTION_KEYS (settings.py) is an ordered list.
encrypt_value() always uses the FIRST key; decrypt_value() tries every
key in order (via a MultiFernet per purpose), so prepending a new key and
redeploying is enough for new writes to use it while existing ciphertext
still decrypts under the previous key. A key can only be safely removed
from the list once every row encrypted under it has been re-saved (which
re-encrypts under the new first key) -- there is no automatic re-encrypt
sweep here; see the H-4 remediation notes for the backfill/rotation
management commands."""
from __future__ import annotations

import base64
import hashlib
import hmac as hmac_module

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings


class FieldDecryptionError(ValueError):
    """A value could not be decrypted under any configured key for its
    purpose -- wrong purpose, corrupted/truncated ciphertext, or every key
    it was encrypted under has since been rotated out."""


def _derive_key(master_key: str, *, purpose: str) -> bytes:
    """One Fernet key per (master key, purpose) pair, so purposes stay
    cryptographically isolated even though they share FIELD_ENCRYPTION_KEYS."""
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=f"hcm-field-encryption:{purpose}".encode())
    return base64.urlsafe_b64encode(hkdf.derive(master_key.encode()))


def _fernet_for(purpose: str) -> MultiFernet:
    return MultiFernet([Fernet(_derive_key(key, purpose=purpose)) for key in settings.FIELD_ENCRYPTION_KEYS])


def encrypt_value(plaintext: str, *, purpose: str) -> str:
    """Encrypts under the FIRST configured key for `purpose`. Returns an
    ASCII token safe to store in a text column."""
    return _fernet_for(purpose).encrypt(plaintext.encode()).decode("ascii")


def decrypt_value(ciphertext: str, *, purpose: str) -> str:
    """Tries every configured key for `purpose`. Raises
    FieldDecryptionError -- never returns silently-wrong plaintext -- if
    none match."""
    try:
        return _fernet_for(purpose).decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise FieldDecryptionError(
            f"Could not decrypt a {purpose!r} value under any configured FIELD_ENCRYPTION_KEYS entry."
        ) from exc


def lookup_fingerprint(value: str, *, purpose: str) -> str:
    """Deterministic, keyed HMAC fingerprint for exact-match lookups on an
    encrypted field, without the unsalted-hash weakness a plain
    sha256(value) would have (spec H-4: "a separate keyed lookup
    fingerprint such as HMAC rather than an unsalted hash"). Not currently
    wired to any model field -- no Restricted field in this codebase is
    queried by exact match today (confirmed by grep: no
    .filter(national_id_number=...) or equivalent anywhere) -- kept here,
    tested, and ready for the day one needs it, rather than bolted onto a
    model without a real use to validate the design against."""
    key = hashlib.sha256(f"hcm-lookup-fingerprint:{purpose}:{settings.FIELD_ENCRYPTION_KEYS[0]}".encode()).digest()
    return hmac_module.new(key, value.encode(), hashlib.sha256).hexdigest()
