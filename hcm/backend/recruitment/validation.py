"""Resume/CV upload validation for the public careers portal (C6 design
spec §4.3). Content-sniffed, not filename-trusted -- same discipline
documents/validation.py established for employee documents.

Duplicated here rather than imported: recruitment may not import documents
(hcm/README.md module rule #1 -- peer apps only through a queries.py seam,
and this is a plain utility function, not a query, so there's no seam that
fits it). This mirrors an existing precedent in this exact codebase:
documents/validation.py's own docstring already duplicates
policies/extraction.py's zip-sniffing for the identical peer-boundary
reason. A future third consumer would be the trigger to promote this into a
shared kernel utility; two independent duplicates is the same amount of
debt this codebase already tolerates today.
"""
from __future__ import annotations

import zipfile

# Tighter than documents.validation.MAX_DOCUMENT_SIZE_BYTES (10MB) -- a CV
# is normally a small text document, unlike a scanned ID or contract.
MAX_RESUME_SIZE_BYTES = 5 * 1024 * 1024

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_JPEG = "image/jpeg"
CONTENT_TYPE_PNG = "image/png"
CONTENT_TYPE_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ResumeValidationError(ValueError):
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


def sniff_resume_content_type(file) -> str:
    """Returns a canonical content-type string, or raises
    ResumeValidationError if the file's actual bytes don't match any
    supported type -- regardless of what its filename claims."""
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
        raise ResumeValidationError("Unsupported file: zip-based file is not a Word document.")
    raise ResumeValidationError(
        "Unsupported or unrecognised file content — allowed: PDF, JPEG, PNG, or Word (.docx)."
    )


def validate_resume_upload(file) -> str:
    """Raises ResumeValidationError for an oversized or unrecognised file;
    otherwise returns the sniffed content type."""
    if file.size > MAX_RESUME_SIZE_BYTES:
        raise ResumeValidationError(
            f"File is too large ({file.size} bytes) — the limit is {MAX_RESUME_SIZE_BYTES} bytes."
        )
    return sniff_resume_content_type(file)
