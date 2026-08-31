from pydantic import BaseModel


class BatchIn(BaseModel):
    applied_ids: list[int] = []
    rejected_ids: list[int] = []
