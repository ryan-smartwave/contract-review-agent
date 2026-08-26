from datetime import datetime, timezone

from src.classifier.schemas import ClassificationResult
from src.intake import service
from src.intake.gmail_client import Attachment, EmailMessage


class FakeGmail:
    def __init__(self, messages):
        self.messages = messages
        self.processed = []

    def fetch_unread_with_attachments(self):
        return self.messages

    def mark_processed(self, message_id):
        self.processed.append(message_id)


def _msg(mid, subject, attachments):
    return EmailMessage(
        message_id=mid, subject=subject, body="",
        received_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        attachments=attachments,
    )


def test_process_inbox_saves_supported_attachments(monkeypatch):
    monkeypatch.setattr(
        service, "classify_and_log",
        lambda document_id, filename, **kw: ClassificationResult(
            is_contract_revision=True, confidence=0.9, reasoning="stub"),
    )
    fake = FakeGmail([
        _msg("m1", "MSA v2 redline", [Attachment("msa-v2.docx", b"docx")]),
        _msg("m2", "Team photo", [Attachment("photo.png", b"png")]),
    ])
    docs = service.process_inbox(fake)
    assert [d.filename for d in docs] == ["msa-v2.docx"]
    assert docs[0].source == "email"
    assert docs[0].detected_at.year == 2026  # detected_at = email received time
    assert fake.processed == ["m1", "m2"]  # both marked, no error on m2


def test_process_inbox_empty_inbox_is_noop():
    assert service.process_inbox(FakeGmail([])) == []
