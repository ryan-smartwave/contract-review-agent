import logging

from fastapi import APIRouter, HTTPException

from src.classifier.service import classify_and_log
from src.documents.extract import FULL_TEXT_MAX_CHARS, extract_text_preview
from src.documents.schemas import DocumentOut
from src.documents.service import is_supported, save_document
from src.locator.drive_client import GOOGLE_DOC_MIME
from src.locator.schemas import DriveConfirmRequest, SearchResponse
from src.locator.service import search_contracts
from src.reviewer.service import run_review

logger = logging.getLogger(__name__)


def get_drive_client():
    from scripts.google_auth import get_credentials
    from src.locator.drive_client import DriveClient

    return DriveClient(get_credentials())


router = APIRouter()


@router.get("/drive/search")
def drive_search(q: str) -> SearchResponse:
    results = search_contracts(q, drive=get_drive_client())
    question = (
        f"I found {len(results)} contracts matching '{q}'. Which one should I review?"
        if len(results) > 1 else None
    )
    return SearchResponse(results=results, clarifying_question=question)


@router.post("/drive/confirm", status_code=201)
def drive_confirm(req: DriveConfirmRequest) -> DocumentOut:
    filename = req.name if req.mime_type != GOOGLE_DOC_MIME else f"{req.name}.pdf"
    if not is_supported(filename):
        raise HTTPException(422, "Only PDF, DOCX, or Google Doc files can be reviewed.")
    content = get_drive_client().download(req.file_id, req.mime_type)
    logger.info("user confirmed drive file %s (%s)", req.name, req.file_id)
    doc = save_document(content, filename, source="drive")
    text = extract_text_preview(content, filename, max_chars=FULL_TEXT_MAX_CHARS)
    result = classify_and_log(doc.id, doc.filename, source="upload", document_text=text)
    if result.is_contract_revision:
        run_review(doc.id, text)
    return DocumentOut(
        id=doc.id, filename=doc.filename, source=doc.source,
        mime_type=doc.mime_type, detected_at=doc.detected_at,
        **result.model_dump(),
    )
