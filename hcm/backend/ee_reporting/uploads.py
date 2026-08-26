"""Content-sniffed validation for EE forum meeting minutes — a deliberate
(smaller) copy of documents/validation.py's approach rather than an import:
`documents` is a peer domain app, not shared kernel, so ee_reporting may
not import it (rbac_audit/test_module_boundaries.py). Two copies don't yet
justify lifting the sniffer into the kernel; a third would (design spec
2026-08-26 §3.2). Minutes are PDF or Word only — no images."""
from __future__ import annotations

import hashlib
import zipfile

MAX_MINUTES_SIZE_BYTES = 10 * 1024 * 1024

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class MinutesValidationError(ValueError):
    pass


def sniff_minutes_content_type(file) -> str:
    file.seek(0)
    head = file.read(8)
    file.seek(0)
    if head.startswith(b"%PDF-"):
        return CONTENT_TYPE_PDF
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(file) as archive:
                if "word/document.xml" in archive.namelist():
                    return CONTENT_TYPE_DOCX
        except zipfile.BadZipFile:
            pass
        finally:
            file.seek(0)
    raise MinutesValidationError("Unsupported or unrecognised file content — minutes must be PDF or Word (.docx).")


def validate_minutes_upload(file) -> tuple[str, str]:
    """Returns (content_type, sha256) or raises MinutesValidationError."""
    if file.size > MAX_MINUTES_SIZE_BYTES:
        raise MinutesValidationError(
            f"File is too large ({file.size} bytes) — the limit is {MAX_MINUTES_SIZE_BYTES} bytes."
        )
    content_type = sniff_minutes_content_type(file)
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return content_type, digest.hexdigest()
