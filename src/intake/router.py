from fastapi import APIRouter, HTTPException, UploadFile

from src.classifier.service import classify_and_log
from src.documents.schemas import DocumentOut
from src.documents.service import is_supported, save_document

router = APIRouter()


@router.post("/upload", status_code=201)
async def upload(file: UploadFile) -> DocumentOut:
    if not is_supported(file.filename or ""):
        raise HTTPException(422, "Unsupported file type. Upload a PDF or DOCX.")
    doc = save_document(await file.read(), file.filename, source="upload")
    result = classify_and_log(doc.id, doc.filename, source="upload")
    return DocumentOut(
        id=doc.id, filename=doc.filename, source=doc.source,
        mime_type=doc.mime_type, detected_at=doc.detected_at,
        **result.model_dump(),
    )
