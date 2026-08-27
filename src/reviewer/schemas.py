from pydantic import BaseModel


class SuggestionDraft(BaseModel):
    clause: str
    original_text: str
    replacement_text: str
    rationale: str


class ReviewResult(BaseModel):
    suggestions: list[SuggestionDraft]
