from src.classifier.service import classify_and_log
from src.documents.models import Document
from src.documents.service import is_supported, save_document
from src.intake.gmail_client import GmailClientProtocol


def process_inbox(client: GmailClientProtocol) -> list[Document]:
    saved: list[Document] = []
    for message in client.fetch_unread_with_attachments():
        for attachment in message.attachments:
            if not is_supported(attachment.filename):
                continue
            doc = save_document(
                attachment.content, attachment.filename,
                source="email", detected_at=message.received_at,
            )
            classify_and_log(
                doc.id, doc.filename, subject=message.subject, body=message.body
            )
            saved.append(doc)
        client.mark_processed(message.message_id)
    return saved
