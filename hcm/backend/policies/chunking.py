from __future__ import annotations

import re

# Character-based proxy for chunk size — real tokenization depends on
# whichever model a future chatbot phase picks (not chosen yet: see the
# Policy Q&A design note in Architecture-Design.md), so this uses the
# common ~4-characters-per-English-token rule of thumb rather than pulling
# in a tokenizer library for a model that doesn't exist yet. ~1000 chars
# is roughly a 250-token passage — a reasonable retrieval-chunk size for
# most embedding models without committing to one.
TARGET_CHUNK_CHARS = 1000

_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, *, target_chars: int = TARGET_CHUNK_CHARS) -> list[str]:
    """Paragraph-aware, deterministic chunking — no ML/embedding
    dependency. Paragraphs are packed greedily up to `target_chars`; a
    single paragraph longer than that is further split on sentence
    boundaries, so no chunk silently swallows an entire long section."""
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush():
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= target_chars:
            current = candidate
            continue

        flush()
        if len(paragraph) <= target_chars:
            current = paragraph
            continue

        for sentence in _SENTENCE_SPLIT_RE.split(paragraph):
            candidate = f"{current} {sentence}".strip() if current else sentence
            if len(candidate) <= target_chars:
                current = candidate
            else:
                flush()
                current = sentence

    flush()
    return chunks
