from datetime import datetime, timezone

from src.classifier.schemas import ClassificationResult
from src.documents import service as documents_service
from src.intake import service
from src.intake.gmail_client import Attachment, EmailMessage, iter_attachment_parts


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


def test_process_inbox_isolates_failed_message(monkeypatch):
    from src.config import settings

    def flaky_classify(document_id, filename, **kw):
        if filename == "msa-v1.docx":
            raise RuntimeError("bad API key")
        return ClassificationResult(is_contract_revision=True, confidence=0.9, reasoning="stub")

    monkeypatch.setattr(service, "classify_and_log", flaky_classify)
    fake = FakeGmail([
        _msg("m1", "MSA v1 redline", [Attachment("msa-v1.docx", b"docx")]),
        _msg("m2", "MSA v2 redline", [Attachment("msa-v2.docx", b"docx")]),
    ])

    docs = service.process_inbox(fake)

    assert [d.filename for d in docs] == ["msa-v2.docx"]
    assert [d.filename for d in documents_service.list_documents()] == ["msa-v2.docx"]
    assert fake.processed == ["m2"]  # m1 stays unread for retry, m2 is done
    remaining_files = list(settings.files_dir.iterdir())
    assert len(remaining_files) == 1  # msa-v1's saved file was rolled back


def test_iter_attachment_parts_finds_nested_and_top_level_attachments():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": "aGk="}},
                    {
                        "mimeType": "multipart/related",
                        "parts": [
                            {
                                "filename": "inline-nested.docx",
                                "body": {"attachmentId": "att-nested"},
                            }
                        ],
                    },
                ],
            },
            {
                "filename": "top-level.pdf",
                "body": {"attachmentId": "att-top"},
            },
        ],
    }
    found = list(iter_attachment_parts(payload))
    filenames = {p["filename"] for p in found}
    assert filenames == {"inline-nested.docx", "top-level.pdf"}
    assert len(found) == 2


def test_iter_attachment_parts_no_attachments_yields_nothing():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": "aGk="}},
            {"mimeType": "text/html", "body": {"data": "aGk="}},
        ],
    }
    assert list(iter_attachment_parts(payload)) == []
