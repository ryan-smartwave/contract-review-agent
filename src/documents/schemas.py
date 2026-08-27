from datetime import datetime, timezone

from pydantic import BaseModel, field_validator

from src.classifier.models import ClassificationLog
from src.documents.models import Document


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    if start.tzinfo:
        start = start.replace(tzinfo=None)
    if end.tzinfo:
        end = end.replace(tzinfo=None)
    return max((end - start).total_seconds(), 0.0)


class DocumentOut(BaseModel):
    id: int
    filename: str
    source: str
    mime_type: str
    detected_at: datetime
    is_contract_revision: bool | None = None
    confidence: float | None = None
    reasoning: str | None = None
    review_seconds: float | None = None

    @field_validator("detected_at")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v

    @classmethod
    def from_document(cls, doc: Document, log: ClassificationLog | None) -> "DocumentOut":
        return cls(
            id=doc.id, filename=doc.filename, source=doc.source,
            mime_type=doc.mime_type, detected_at=doc.detected_at,
            is_contract_revision=log.is_contract_revision if log else None,
            confidence=log.confidence if log else None,
            reasoning=log.reasoning if log else None,
            review_seconds=_seconds_between(doc.detected_at, doc.review_ready_at),
        )


class SuggestionOut(BaseModel):
    id: int
    clause: str
    original_text: str
    replacement_text: str
    rationale: str
    status: str


class VersionOut(BaseModel):
    version_number: int
    source_suggestion_id: int | None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v


class DocumentDetailOut(DocumentOut):
    text: str
    suggestions: list[SuggestionOut]
    versions: list[VersionOut]


def document_detail(document_id: int) -> DocumentDetailOut:
    from src.classifier.service import get_log
    from src.documents.service import get_document, latest_version, list_versions
    from src.reviewer.service import list_suggestions

    doc = get_document(document_id)
    if doc is None:
        raise LookupError(document_id)
    base = DocumentOut.from_document(doc, get_log(document_id))
    version = latest_version(document_id)
    return DocumentDetailOut(
        **base.model_dump(),
        text=version.text_content if version else "",
        suggestions=[SuggestionOut(**s.model_dump()) for s in list_suggestions(document_id)],
        versions=[VersionOut(**v.model_dump()) for v in list_versions(document_id)],
    )
