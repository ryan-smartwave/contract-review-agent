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


def extract_plain_body(payload: dict) -> str:
    """Recursively find the first text/plain part's body.data (base64url,
    padding-safe) and decode it; return "" if none."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                "utf-8", errors="replace"
            )
    for part in payload.get("parts", []):
        text = extract_plain_body(part)
        if text:
            return text
    return ""


def iter_attachment_parts(payload: dict):
    """Yield every part in the payload tree that has both a filename and a
    body attachmentId, walking nested multipart parts recursively."""
    filename = payload.get("filename")
    att_id = payload.get("body", {}).get("attachmentId")
    if filename and att_id:
        yield payload
    for part in payload.get("parts", []):
        yield from iter_attachment_parts(part)


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
        for part in iter_attachment_parts(msg["payload"]):
            filename = part["filename"]
            att_id = part["body"]["attachmentId"]
            data = self._svc.users().messages().attachments().get(
                userId="me", messageId=message_id, id=att_id
            ).execute()["data"]
            padded = data + "=" * (-len(data) % 4)
            attachments.append(Attachment(filename, base64.urlsafe_b64decode(padded)))
        return EmailMessage(
            message_id=message_id,
            subject=headers.get("subject", ""),
            body=extract_plain_body(msg["payload"]) or msg.get("snippet", ""),
            received_at=received,
            attachments=attachments,
        )
