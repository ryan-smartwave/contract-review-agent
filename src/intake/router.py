from fastapi import APIRouter, HTTPException, UploadFile

from src.documents.schemas import DocumentOut
from src.documents.service import is_supported
from src.intake import pipeline

router = APIRouter()


@router.post("/upload", status_code=201)
async def upload(file: UploadFile) -> DocumentOut:
    content = await file.read()
    if not is_supported(file.filename or ""):
        raise HTTPException(422, "Unsupported file type. Upload a PDF or DOCX.")
    try:
        doc, result = pipeline.ingest_document(content, file.filename, source="upload")
    except pipeline.ClassificationFailedError:
        raise HTTPException(
            502, "The document was received but classification failed. Please try again."
        )
    return DocumentOut(
        id=doc.id, filename=doc.filename, source=doc.source,
        mime_type=doc.mime_type, detected_at=doc.detected_at,
        **result.model_dump(),
    )
