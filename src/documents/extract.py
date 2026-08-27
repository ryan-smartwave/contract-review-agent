import logging
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

PREVIEW_MAX_CHARS = 4000
FULL_TEXT_MAX_CHARS = 50_000


def extract_text_preview(content: bytes, filename: str, max_chars: int = PREVIEW_MAX_CHARS) -> str:
    """Best-effort text from the document; empty string on any failure.

    Reads only as many pages/paragraphs as needed to reach max_chars.
    """
    try:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            text = _pdf_text(content, max_chars)
        elif ext == ".docx":
            text = _docx_text(content)
        else:
            return ""
        return " ".join(text.split())[:max_chars]
    except Exception:
        logger.warning("text extraction failed for %s", filename, exc_info=True)
        return ""


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

    return "\n".join(paragraph.text for paragraph in Document(BytesIO(content)).paragraphs)
