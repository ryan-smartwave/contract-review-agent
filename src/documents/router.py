from fastapi import APIRouter

from src.classifier.service import get_log
from src.documents.schemas import DocumentOut
from src.documents.service import list_documents

router = APIRouter()


@router.get("/documents")
def documents() -> list[DocumentOut]:
    return [DocumentOut.from_document(d, get_log(d.id)) for d in list_documents()]
