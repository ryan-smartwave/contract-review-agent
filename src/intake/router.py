from fastapi import APIRouter, HTTPException, UploadFile

from src.classifier.service import classify_and_log
from src.documents.extract import FULL_TEXT_MAX_CHARS, extract_text_preview
from src.documents.schemas import DocumentOut
from src.documents.service import is_supported, save_document

router = APIRouter()


@router.post("/upload", status_code=201)
async def upload(file: UploadFile) -> DocumentOut:
    content = await file.read()
    if not is_supported(file.filename or ""):
        raise HTTPException(422, "Unsupported file type. Upload a PDF or DOCX.")
    doc = save_document(content, file.filename, source="upload")
    text = extract_text_preview(content, file.filename, max_chars=FULL_TEXT_MAX_CHARS)
    result = classify_and_log(doc.id, doc.filename, source="upload", document_text=text)
    return DocumentOut(
        id=doc.id, filename=doc.filename, source=doc.source,
        mime_type=doc.mime_type, detected_at=doc.detected_at,
        **result.model_dump(),
    )
