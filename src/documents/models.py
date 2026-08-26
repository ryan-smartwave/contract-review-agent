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
