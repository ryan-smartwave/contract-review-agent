import logging

from fastapi import APIRouter, HTTPException

from src.documents.schemas import DocumentOut
from src.documents.service import is_supported
from src.intake import pipeline
from src.locator.drive_client import GOOGLE_DOC_MIME
from src.locator.schemas import DriveConfirmRequest, SearchResponse
from src.locator.service import search_contracts

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
    try:
        doc, result = pipeline.ingest_document(content, filename, source="drive")
    except pipeline.ClassificationFailedError:
        raise HTTPException(
            502, "The document was received but classification failed. Please try again."
        )
    return DocumentOut(
        id=doc.id, filename=doc.filename, source=doc.source,
        mime_type=doc.mime_type, detected_at=doc.detected_at,
        **result.model_dump(),
    )
