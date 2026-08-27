import logging

from fastapi import APIRouter, HTTPException, UploadFile

from src.classifier.service import classify_and_log
from src.documents.extract import FULL_TEXT_MAX_CHARS, extract_text_preview
from src.documents.schemas import DocumentOut
from src.documents.service import delete_document, is_supported, save_document
from src.reviewer.service import run_review

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload", status_code=201)
async def upload(file: UploadFile) -> DocumentOut:
    content = await file.read()
    if not is_supported(file.filename or ""):
        raise HTTPException(422, "Unsupported file type. Upload a PDF or DOCX.")
    doc = save_document(content, file.filename, source="upload")
    text = extract_text_preview(content, file.filename, max_chars=FULL_TEXT_MAX_CHARS)
    try:
        result = classify_and_log(doc.id, doc.filename, source="upload", document_text=text)
    except Exception:
        logger.exception("classification failed for upload %s", doc.filename)
        delete_document(doc)
        raise HTTPException(
            502, "The document was received but classification failed. Please try again."
        )
    if result.is_contract_revision:
        try:
            run_review(doc.id, text)
        except Exception:
            logger.exception("review failed for %s; suggestions unavailable", doc.filename)
    return DocumentOut(
        id=doc.id, filename=doc.filename, source=doc.source,
        mime_type=doc.mime_type, detected_at=doc.detected_at,
        **result.model_dump(),
    )
