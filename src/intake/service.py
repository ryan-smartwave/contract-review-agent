import logging

from src.classifier.service import classify_and_log
from src.comparator.service import run_comparison
from src.documents.extract import FULL_TEXT_MAX_CHARS, extract_text_preview
from src.documents.models import Document
from src.documents.service import delete_document, is_supported, save_document
from src.intake.gmail_client import GmailClientProtocol
from src.reviewer.service import run_review

logger = logging.getLogger(__name__)


def process_inbox(client: GmailClientProtocol) -> list[Document]:
    saved: list[Document] = []
    for message in client.fetch_unread_with_attachments():
        message_docs: list[Document] = []
        try:
            for attachment in message.attachments:
                if not is_supported(attachment.filename):
                    continue
                doc = save_document(
                    attachment.content, attachment.filename,
                    source="email", detected_at=message.received_at,
                )
                message_docs.append(doc)
                text = extract_text_preview(
                    attachment.content, attachment.filename, max_chars=FULL_TEXT_MAX_CHARS
                )
                result = classify_and_log(
                    doc.id, doc.filename, subject=message.subject,
                    body=message.body, document_text=text,
                )
                if result.is_contract_revision:
                    run_review(doc.id, text)
                    try:
                        run_comparison(doc.id, text)
                    except Exception:
                        logger.exception(
                            "comparison failed for %s; comparison unavailable", doc.filename
                        )
        except Exception:
            logger.exception("failed to process message %s; leaving unread for retry", message.message_id)
            for doc in message_docs:
                delete_document(doc)
            continue
        saved.extend(message_docs)
        client.mark_processed(message.message_id)
    return saved
