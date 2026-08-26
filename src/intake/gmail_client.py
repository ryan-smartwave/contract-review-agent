import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from googleapiclient.discovery import build


@dataclass
class Attachment:
    filename: str
    content: bytes


@dataclass
class EmailMessage:
    message_id: str
    subject: str
    body: str
    received_at: datetime
    attachments: list[Attachment] = field(default_factory=list)


class GmailClientProtocol(Protocol):
    def fetch_unread_with_attachments(self) -> list[EmailMessage]: ...
    def mark_processed(self, message_id: str) -> None: ...


class GmailClient:
    def __init__(self, credentials):
        self._svc = build("gmail", "v1", credentials=credentials)

    def fetch_unread_with_attachments(self) -> list[EmailMessage]:
        listing = self._svc.users().messages().list(
            userId="me", q="is:unread has:attachment", maxResults=10
        ).execute()
        return [self._fetch(m["id"]) for m in listing.get("messages", [])]

    def mark_processed(self, message_id: str) -> None:
        self._svc.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()

    def _fetch(self, message_id: str) -> EmailMessage:
        msg = self._svc.users().messages().get(userId="me", id=message_id).execute()
        headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
        received = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)
        attachments = []
        for part in msg["payload"].get("parts", []):
            filename = part.get("filename")
            att_id = part.get("body", {}).get("attachmentId")
            if filename and att_id:
                data = self._svc.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=att_id
                ).execute()["data"]
                attachments.append(Attachment(filename, base64.urlsafe_b64decode(data)))
        return EmailMessage(
            message_id=message_id,
            subject=headers.get("subject", ""),
            body=msg.get("snippet", ""),
            received_at=received,
            attachments=attachments,
        )
