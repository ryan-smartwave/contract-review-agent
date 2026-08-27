from datetime import datetime

from sqlmodel import Field, SQLModel

from src.documents.models import utcnow


class Suggestion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    clause: str
    original_text: str
    replacement_text: str
    rationale: str
    status: str = "pending"  # pending | applied | rejected | stale
    created_at: datetime = Field(default_factory=utcnow)
