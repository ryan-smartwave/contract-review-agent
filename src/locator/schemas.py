from datetime import datetime

from pydantic import BaseModel


class DriveFile(BaseModel):
    file_id: str
    name: str
    modified_time: datetime
    mime_type: str
    web_view_link: str | None = None
