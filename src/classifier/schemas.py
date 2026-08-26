from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    is_contract_revision: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
