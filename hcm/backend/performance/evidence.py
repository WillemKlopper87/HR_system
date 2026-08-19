"""Content sniffing + size cap for `EvidenceItem` file uploads (PC-2).

Evidence can be any of the file types someone would actually attach to a
KPI (a spreadsheet extract, a screenshot, a signed-off PDF, a scanned
register) -- unlike `policies.extraction`, there is nothing to *extract*
here, just a check that the bytes match a declared, known-safe kind before
they're stored (a renamed `.exe` doesn't get to ride in as `evidence.pdf`)
and a hard size cap, same "sniff first, clean 400 on mismatch" shape as
`policies/extraction.py`.
"""
from __future__ import annotations

MAX_EVIDENCE_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class UnsupportedEvidenceFileError(ValueError):
    pass


def _starts_with(head: bytes, *signatures: bytes) -> bool:
    return any(head.startswith(sig) for sig in signatures)


def validate_evidence_file(file) -> None:
    """Raises `UnsupportedEvidenceFileError` for an oversized or
    content-mismatched upload. Called from `EvidenceItemSerializer.validate`
    before the file is ever saved."""
    if file.size > MAX_EVIDENCE_FILE_SIZE:
        raise UnsupportedEvidenceFileError(
            f"That file is {file.size / (1024 * 1024):.1f} MB — evidence uploads are capped at 20 MB."
        )

    file.seek(0)
    head = file.read(8)
    file.seek(0)

    is_pdf = _starts_with(head, b"%PDF-")
    is_jpeg = _starts_with(head, b"\xff\xd8\xff")
    is_png = _starts_with(head, b"\x89PNG\r\n\x1a\n")
    is_gif = _starts_with(head, b"GIF87a", b"GIF89a")
    # docx/xlsx/pptx are zip archives under the hood, same magic as policies' .docx check
    is_office_zip = _starts_with(head, b"PK\x03\x04")
    if is_pdf or is_jpeg or is_png or is_gif or is_office_zip:
        return

    # Fall back to "looks like text" (no NUL bytes) for CSV/TXT evidence exports.
    sample = head + file.read(4096)
    file.seek(0)
    if b"\x00" not in sample:
        return

    raise UnsupportedEvidenceFileError(
        "That file's content doesn't match a supported evidence type "
        "(PDF, image, Office document, or plain text/CSV)."
    )
