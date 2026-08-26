from datetime import datetime

from sqlmodel import Field, SQLModel

from src.documents.models import utcnow


class ClassificationLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    is_contract_revision: bool
    confidence: float
    reasoning: str
    created_at: datetime = Field(default_factory=utcnow)
