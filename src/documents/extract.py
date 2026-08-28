import logging
import re
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

PREVIEW_MAX_CHARS = 4000
FULL_TEXT_MAX_CHARS = 50_000

_CLAUSE_START = re.compile(r"\d{1,2}\.\s+\S")


def extract_text_preview(content: bytes, filename: str, max_chars: int = PREVIEW_MAX_CHARS) -> str:
    """Best-effort text from the document; empty string on any failure.

    Paragraphs are preserved as blank-line separators ("\\n\\n"); whitespace
    inside a paragraph is collapsed. Reads only as many pages as needed to
    reach max_chars.
    """
    try:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            text = _to_paragraphs(_pdf_text(content, max_chars))
        elif ext == ".docx":
            text = _docx_text(content)
        else:
            return ""
        return text[:max_chars]
    except Exception:
        logger.warning("text extraction failed for %s", filename, exc_info=True)
        return ""


def _to_paragraphs(raw: str) -> str:
    """Merge layout lines into paragraphs; blank lines and numbered clause
    starts (e.g. "3. LIABILITY...") begin a new paragraph."""
    paragraphs: list[list[str]] = [[]]
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            if paragraphs[-1]:
                paragraphs.append([])
            continue
        if _CLAUSE_START.match(stripped) and paragraphs[-1]:
            paragraphs.append([])
        paragraphs[-1].append(stripped)
    return "\n\n".join(" ".join(" ".join(p).split()) for p in paragraphs if p)


def _pdf_text(content: bytes, max_chars: int) -> str:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    pages = []
    accumulated = 0
    for page in reader.pages:
        page_text = page.extract_text() or ""
        pages.append(page_text)
        accumulated += len(page_text)
        if accumulated >= max_chars:
            break
    return "\n".join(pages)


def _docx_text(content: bytes) -> str:
    from docx import Document

    return "\n\n".join(
        " ".join(paragraph.text.split())
        for paragraph in Document(BytesIO(content)).paragraphs
        if paragraph.text.strip()
    )
