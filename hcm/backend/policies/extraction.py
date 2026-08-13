from __future__ import annotations

from docx import Document as DocxDocument
from pypdf import PdfReader

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


class UnsupportedDocumentError(ValueError):
    pass


def extract_text(file) -> str:
    """Extracts plain text from an uploaded policy document. Deliberately
    no OCR — a scanned/image-only PDF yields empty or near-empty text,
    which callers (policies/services.py) treat as an extraction failure
    rather than silently publishing a blank policy."""
    name = (getattr(file, "name", "") or "").lower()
    file.seek(0)

    if name.endswith(".pdf"):
        reader = PdfReader(file)
        return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()

    if name.endswith(".docx"):
        document = DocxDocument(file)
        return "\n\n".join(p.text for p in document.paragraphs if p.text.strip()).strip()

    if name.endswith((".txt", ".md")):
        raw = file.read()
        return raw.decode("utf-8", errors="replace").strip()

    raise UnsupportedDocumentError(
        f"Unsupported document type: {name or '(unknown filename)'}. "
        f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}."
    )
