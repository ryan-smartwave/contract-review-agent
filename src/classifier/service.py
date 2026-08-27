from sqlmodel import select

from src.classifier.models import ClassificationLog
from src.classifier.schemas import ClassificationResult
from src.documents import db
from src.llm.factory import get_chat_model

BODY_MAX_CHARS = 2000
DOC_TEXT_MAX_CHARS = 4000

EMAIL_PROMPT = """You are a legal-operations email triage assistant.
Decide whether this email + attachment is a CONTRACT REVISION \
(a new draft, redline, or amendment of a contract) or not \
(invoice, newsletter, receipt, general correspondence, etc.).
Judge primarily from the document text when present; filenames can be misleading.

Attachment filename: {filename}
Email subject: {subject}
Email body (may be truncated or empty): {body}
Document text (first pages; may be empty): {document_text}
"""

UPLOAD_PROMPT = """You are a legal-operations document triage assistant.
A user manually uploaded this document for contract review.
Decide whether it is a CONTRACT REVISION \
(a new draft, redline, or amendment of a contract) or not \
(invoice, newsletter, receipt, other paperwork, etc.).
Judge primarily from the document text when present; filenames can be misleading.

Uploaded filename: {filename}
Document text (first pages; may be empty): {document_text}
"""


def classify_and_log(
    document_id: int,
    filename: str,
    subject: str = "",
    body: str = "",
    source: str = "email",
    document_text: str = "",
    llm=None,
) -> ClassificationResult:
    llm = llm or get_chat_model()
    structured = llm.with_structured_output(ClassificationResult)
    document_text = document_text[:DOC_TEXT_MAX_CHARS]
    if source == "upload":
        prompt = UPLOAD_PROMPT.format(filename=filename, document_text=document_text)
    else:
        prompt = EMAIL_PROMPT.format(
            filename=filename, subject=subject, body=body[:BODY_MAX_CHARS],
            document_text=document_text,
        )
    result = structured.invoke(prompt)
    with db.get_session() as session:
        session.add(ClassificationLog(document_id=document_id, **result.model_dump()))
        session.commit()
    return result


def get_log(document_id: int) -> ClassificationLog | None:
    with db.get_session() as session:
        return session.exec(
            select(ClassificationLog)
            .where(ClassificationLog.document_id == document_id)
            .order_by(ClassificationLog.created_at.desc())
        ).first()
