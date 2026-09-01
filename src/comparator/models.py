from datetime import datetime

from sqlmodel import Field, SQLModel

from src.documents.models import utcnow


class Comparison(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    matched_document_id: int | None = None
    status: str  # "ready" | "no_match" | "failed"
    summary: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ComparisonChange(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    comparison_id: int = Field(index=True)
    kind: str  # "added" | "removed" | "modified"
    clause: str
    before_text: str | None = None
    after_text: str | None = None
    note: str
