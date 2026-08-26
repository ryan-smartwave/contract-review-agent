from datetime import datetime

from googleapiclient.discovery import build

from src.locator.schemas import DriveFile

CONTRACT_MIMES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.document",
)


class DriveClient:
    def __init__(self, credentials):
        self._svc = build("drive", "v3", credentials=credentials)

    def search(self, q: str) -> list[DriveFile]:
        mime_clause = " or ".join(f"mimeType='{m}'" for m in CONTRACT_MIMES)
        escaped = q.replace("'", r"\'")
        listing = self._svc.files().list(
            q=f"name contains '{escaped}' and ({mime_clause}) and trashed=false",
            fields="files(id,name,modifiedTime,mimeType,webViewLink)",
            pageSize=10,
        ).execute()
        return [
            DriveFile(
                file_id=f["id"], name=f["name"], mime_type=f["mimeType"],
                modified_time=datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00")),
                web_view_link=f.get("webViewLink"),
            )
            for f in listing.get("files", [])
        ]
