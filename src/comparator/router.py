from fastapi import APIRouter, HTTPException

from src.comparator.schemas import ChangeOut, ComparisonOut, MatchedDocumentOut
from src.comparator.service import get_comparison
from src.documents.service import get_document

router = APIRouter()


@router.get("/documents/{document_id}/comparison")
def comparison(document_id: int) -> ComparisonOut:
    if get_document(document_id) is None:
        raise HTTPException(404, "Document not found")
    stored = get_comparison(document_id)
    if stored is None:
        return ComparisonOut(status="pending")
    record, changes = stored
    matched = get_document(record.matched_document_id) if record.matched_document_id else None
    return ComparisonOut(
        status=record.status,
        matched_document=(
            MatchedDocumentOut(id=matched.id, filename=matched.filename,
                               detected_at=matched.detected_at)
            if matched else None
        ),
        summary=record.summary,
        changes=[ChangeOut(kind=c.kind, clause=c.clause, before_text=c.before_text,
                           after_text=c.after_text, note=c.note) for c in changes],
    )
