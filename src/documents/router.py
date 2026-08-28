from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from src.classifier.service import get_log
from src.documents.schemas import DocumentDetailOut, DocumentOut, document_detail
from src.documents.service import MIME_TYPES, get_document, get_version, list_documents

router = APIRouter()


@router.get("/documents")
def documents() -> list[DocumentOut]:
    return [DocumentOut.from_document(d, get_log(d.id)) for d in list_documents()]


@router.get("/documents/{document_id}/file")
def document_file(document_id: int) -> FileResponse:
    doc = get_document(document_id)
    if doc is None or not Path(doc.file_path).exists():
        raise HTTPException(404, "Document file not found")
    return FileResponse(doc.file_path, media_type=doc.mime_type, filename=doc.filename)


@router.get("/documents/{document_id}/versions/{version_number}/file")
def version_file(document_id: int, version_number: int) -> FileResponse:
    doc = get_document(document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    version = get_version(document_id, version_number)
    if version is None:
        raise HTTPException(404, "Version not found")
    if version.file_path:
        if not Path(version.file_path).exists():
            raise HTTPException(404, "Version file not found")
        return FileResponse(
            version.file_path, media_type=MIME_TYPES[".docx"], filename=version.filename
        )
    if version_number == 1:
        if not Path(doc.file_path).exists():
            raise HTTPException(404, "Document file not found")
        return FileResponse(doc.file_path, media_type=doc.mime_type, filename=doc.filename)
    raise HTTPException(404, "Version file not found")


@router.get("/documents/{document_id}")
def document(document_id: int) -> DocumentDetailOut:
    try:
        return document_detail(document_id)
    except LookupError:
        raise HTTPException(404, "Document not found")
