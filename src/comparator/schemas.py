from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# --- LLM structured output ---

class MatchResult(BaseModel):
    matched_document_id: int | None
    reason: str


class ChangeDraft(BaseModel):
    kind: Literal["added", "removed", "modified"]
    clause: str
    before_text: str | None = None
    after_text: str | None = None
    note: str


class CompareResult(BaseModel):
    summary: str
    changes: list[ChangeDraft]


# --- API output ---

class MatchedDocumentOut(BaseModel):
    id: int
    filename: str
    detected_at: datetime


class ChangeOut(BaseModel):
    kind: str
    clause: str
    before_text: str | None
    after_text: str | None
    note: str


class ComparisonOut(BaseModel):
    status: str  # "pending" | "ready" | "no_match" | "failed"
    matched_document: MatchedDocumentOut | None = None
    summary: str | None = None
    changes: list[ChangeOut] = []
