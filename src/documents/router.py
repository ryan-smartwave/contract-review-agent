from fastapi import APIRouter, HTTPException

from src.classifier.service import get_log
from src.documents.schemas import DocumentDetailOut, DocumentOut, document_detail
from src.documents.service import list_documents

router = APIRouter()


@router.get("/documents")
def documents() -> list[DocumentOut]:
    return [DocumentOut.from_document(d, get_log(d.id)) for d in list_documents()]


@router.get("/documents/{document_id}")
def document(document_id: int) -> DocumentDetailOut:
    try:
        return document_detail(document_id)
    except LookupError:
        raise HTTPException(404, "Document not found")
