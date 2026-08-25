"""Upload validation for documents.EmployeeDocument — content-sniffed, not
filename-trusted (design spec §2 intro / brief: "a prior review flagged
that policy uploads were validated by filename extension only"). Same
defect class policies/extraction.py already fixed for policy uploads; this
is the equivalent fix here, but simpler — EmployeeDocument never extracts
text, it only needs to know "is this really the kind of file it claims to
be" and "is it small enough", so this sniffs magic bytes rather than
parsing the document."""
from __future__ import annotations

import zipfile

# Generous for a scanned ID/contract PDF or a phone photo of a certificate,
# without accepting arbitrarily large uploads. Tighter than the platform-
# wide DATA_UPLOAD_MAX_MEMORY_SIZE (20MB, config/settings.py) — that cap
# exists so Django doesn't buffer an enormous request body in memory at
# all; this is a document-specific ceiling on top of it.
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_JPEG = "image/jpeg"
CONTENT_TYPE_PNG = "image/png"
CONTENT_TYPE_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentValidationError(ValueError):
    pass


def _sniff_docx(file) -> str | None:
    """A .docx is a zip archive (same check as policies/extraction.py's
    DOCX handling) — narrowed to specifically a Word document, not just
    any zip, by checking for word/document.xml inside it."""
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


def sniff_content_type(file) -> str:
    """Returns a canonical content-type string, or raises
    DocumentValidationError if the file's actual bytes don't match any
    supported document type — regardless of what its filename claims."""
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
        raise DocumentValidationError("Unsupported document: zip-based file is not a Word document.")
    raise DocumentValidationError(
        "Unsupported or unrecognised file content — allowed: PDF, JPEG, PNG, or Word (.docx)."
    )


def validate_upload(file) -> str:
    """Raises DocumentValidationError for an oversized or unrecognised
    file; otherwise returns the sniffed content type."""
    if file.size > MAX_DOCUMENT_SIZE_BYTES:
        raise DocumentValidationError(
            f"File is too large ({file.size} bytes) — the limit is {MAX_DOCUMENT_SIZE_BYTES} bytes."
        )
    return sniff_content_type(file)
