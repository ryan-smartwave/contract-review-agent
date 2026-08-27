from datetime import datetime

from pydantic import BaseModel


class DriveFile(BaseModel):
    file_id: str
    name: str
    modified_time: datetime
    mime_type: str
    web_view_link: str | None = None


class SearchResponse(BaseModel):
    results: list[DriveFile]
    clarifying_question: str | None = None


class DriveConfirmRequest(BaseModel):
    file_id: str
    name: str
    mime_type: str
