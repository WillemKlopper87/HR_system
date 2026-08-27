"""Content-sniffed validation for TrainingRecord's B-BBEE skills-development
evidence file (provider invoice / attendance register / learner agreement) --
same discipline documents/validation.py established, duplicated rather than
imported because learning may not import documents (hcm/README.md module
rule #1 -- peer apps only through a queries.py seam, and this is a plain
utility function, not a query). recruitment/validation.py and
ee_reporting/uploads.py already carry their own copies of this exact
sniffer for the identical peer-boundary reason; this is a fourth."""
from __future__ import annotations

import hashlib
import zipfile

MAX_EVIDENCE_SIZE_BYTES = 10 * 1024 * 1024

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_JPEG = "image/jpeg"
CONTENT_TYPE_PNG = "image/png"
CONTENT_TYPE_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class EvidenceValidationError(ValueError):
    pass


def _sniff_docx(file) -> str | None:
    file.seek(0)
    try:
        with zipfile.ZipFile(file) as archive:
            if "word/document.xml" in archive.namelist():
                return CONTENT_TYPE_DOCX
    except zipfile.BadZipFile:
        pass
    finally:
        file.seek(0)
    return None


def sniff_evidence_content_type(file) -> str:
    file.seek(0)
    head = file.read(8)
    file.seek(0)
    if head.startswith(b"%PDF-"):
        return CONTENT_TYPE_PDF
    if head.startswith(b"\xff\xd8\xff"):
        return CONTENT_TYPE_JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return CONTENT_TYPE_PNG
    if head.startswith(b"PK\x03\x04"):
        docx_type = _sniff_docx(file)
        if docx_type is not None:
            return docx_type
        raise EvidenceValidationError("Unsupported file: zip-based file is not a Word document.")
    raise EvidenceValidationError(
        "Unsupported or unrecognised file content — allowed: PDF, JPEG, PNG, or Word (.docx)."
    )


def validate_evidence_upload(file) -> tuple[str, str]:
    """Returns (content_type, sha256) or raises EvidenceValidationError."""
    if file.size > MAX_EVIDENCE_SIZE_BYTES:
        raise EvidenceValidationError(
            f"File is too large ({file.size} bytes) — the limit is {MAX_EVIDENCE_SIZE_BYTES} bytes."
        )
    content_type = sniff_evidence_content_type(file)
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return content_type, digest.hexdigest()
