from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase

from .management.commands.verify_restored_artifacts import verify_signed_documents


class _StoredFile:
    def __init__(self, content: bytes | None):
        self.content = content

    def open(self, _mode):
        if self.content is None:
            raise FileNotFoundError("missing.pdf")
        return BytesIO(self.content)


class _Related:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class RestoreArtifactVerificationTests(TestCase):
    def _document(self, content=b"signed PDF", stored_hash=None, signature_hash=None):
        import hashlib

        stored_hash = stored_hash or hashlib.sha256(content).hexdigest()
        signature_hash = signature_hash or stored_hash
        return SimpleNamespace(
            pk=7,
            pdf=_StoredFile(content),
            sha256=stored_hash,
            signatures=_Related([SimpleNamespace(pk=11, document_sha256=signature_hash)]),
        )

    def test_matching_restored_document_and_signature_pass(self):
        checked, problems = verify_signed_documents([self._document()])
        self.assertEqual(checked, 1)
        self.assertEqual(problems, [])

    def test_tampered_media_is_reported(self):
        document = self._document(stored_hash="0" * 64, signature_hash="0" * 64)
        _checked, problems = verify_signed_documents([document])
        self.assertIn("restored media hash does not match", problems[0])

    def test_signature_hash_mismatch_is_reported(self):
        document = self._document(signature_hash="f" * 64)
        _checked, problems = verify_signed_documents([document])
        self.assertIn("signature 11 records a different hash", problems[0])

    def test_missing_media_is_reported(self):
        document = self._document()
        document.pdf = _StoredFile(None)
        _checked, problems = verify_signed_documents([document])
        self.assertIn("media unavailable", problems[0])
