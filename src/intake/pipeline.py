import logging

from src.classifier.schemas import ClassificationResult
from src.classifier.service import classify_and_log
from src.comparator.service import run_comparison
from src.documents.extract import FULL_TEXT_MAX_CHARS, extract_text_preview
from src.documents.models import Document
from src.documents.service import delete_document, save_document
from src.reviewer.service import run_review

logger = logging.getLogger(__name__)


class ClassificationFailedError(Exception):
    pass


def ingest_document(content: bytes, filename: str, source: str) -> tuple[Document, ClassificationResult]:
    """Save + classify + (best-effort) review. Rolls back the document if
    classification fails; a review failure only logs — doc + classification stand."""
    doc = save_document(content, filename, source=source)
    text = extract_text_preview(content, filename, max_chars=FULL_TEXT_MAX_CHARS)
    try:
        result = classify_and_log(doc.id, doc.filename, source="upload", document_text=text)
    except Exception as exc:
        logger.exception("classification failed for %s", filename)
        delete_document(doc)
        raise ClassificationFailedError(filename) from exc
    if result.is_contract_revision:
        try:
            run_review(doc.id, text)
        except Exception:
            logger.exception("review failed for %s; suggestions unavailable", filename)
        try:
            run_comparison(doc.id, text)
        except Exception:
            logger.exception("comparison failed for %s; comparison unavailable", filename)
    return doc, result
