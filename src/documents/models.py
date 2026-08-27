from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str
    file_path: str
    source: str  # "email" | "upload"
    mime_type: str
    detected_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
    review_ready_at: datetime | None = None


class DocumentVersion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    version_number: int
    text_content: str
    source_suggestion_id: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
