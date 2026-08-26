from datetime import datetime, timezone

from pydantic import BaseModel, field_validator

from src.classifier.models import ClassificationLog
from src.documents.models import Document


class DocumentOut(BaseModel):
    id: int
    filename: str
    source: str
    mime_type: str
    detected_at: datetime
    is_contract_revision: bool | None = None
    confidence: float | None = None
    reasoning: str | None = None

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
        )
