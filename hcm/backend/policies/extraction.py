from __future__ import annotations

import zipfile

from docx import Document as DocxDocument
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


class UnsupportedDocumentError(ValueError):
    pass


def _sniff(file, n: int) -> bytes:
    file.seek(0)
    head = file.read(n)
    file.seek(0)
    return head


def extract_text(file) -> str:
    """Extracts plain text from an uploaded policy document. Deliberately
    no OCR — a scanned/image-only PDF yields empty or near-empty text,
    which callers (policies/services.py) treat as an extraction failure
    rather than silently publishing a blank policy.

    The extension picks the parser but is *not* trusted on its own (H2,
    brief D4): the content is sniffed first (PDF magic, zip magic for
    DOCX, "no NUL bytes" for text) and parser failures are wrapped, so a
    mislabelled or corrupt upload is a clean 400 to the caller instead of a
    500 from pypdf/python-docx."""
    name = (getattr(file, "name", "") or "").lower()
    file.seek(0)

    if name.endswith(".pdf"):
        if not _sniff(file, 5).startswith(b"%PDF-"):
            raise UnsupportedDocumentError("The uploaded file does not look like a PDF (wrong content for a .pdf name).")
        try:
            reader = PdfReader(file)
            return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception as exc:  # noqa: BLE001 — pypdf raises a zoo of exception types
            raise UnsupportedDocumentError(f"The PDF could not be read: {exc}") from exc

    if name.endswith(".docx"):
        if not _sniff(file, 4).startswith(b"PK\x03\x04"):
            raise UnsupportedDocumentError(
                "The uploaded file does not look like a Word document (a .docx is a zip archive)."
            )
        try:
            file.seek(0)
            with zipfile.ZipFile(file) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise UnsupportedDocumentError("The uploaded zip is not a Word document (no word/document.xml).")
            file.seek(0)
            document = DocxDocument(file)
            return "\n\n".join(p.text for p in document.paragraphs if p.text.strip()).strip()
        except UnsupportedDocumentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise UnsupportedDocumentError(f"The Word document could not be read: {exc}") from exc

    if name.endswith((".txt", ".md")):
        raw = file.read()
        if b"\x00" in raw[:4096]:
            raise UnsupportedDocumentError("The uploaded file is not a text file (binary content).")
        return raw.decode("utf-8", errors="replace").strip()

    raise UnsupportedDocumentError(
        f"Unsupported document type: {name or '(unknown filename)'}. "
        f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}."
    )
