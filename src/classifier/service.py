from sqlmodel import select

from src.classifier.models import ClassificationLog
from src.classifier.schemas import ClassificationResult
from src.documents import db
from src.llm.factory import get_chat_model

EMAIL_PROMPT = """You are a legal-operations email triage assistant.
Decide whether this email + attachment is a CONTRACT REVISION \
(a new draft, redline, or amendment of a contract) or not \
(invoice, newsletter, receipt, general correspondence, etc.).

Attachment filename: {filename}
Email subject: {subject}
Email body (may be empty): {body}
"""

UPLOAD_PROMPT = """You are a legal-operations document triage assistant.
A user manually uploaded this document for contract review.
Decide whether it is a CONTRACT REVISION \
(a new draft, redline, or amendment of a contract) or not \
(invoice, newsletter, receipt, other paperwork, etc.).
Judge from the document itself; there is no accompanying message.

Uploaded filename: {filename}
"""


def classify_and_log(
    document_id: int,
    filename: str,
    subject: str = "",
    body: str = "",
    source: str = "email",
    llm=None,
) -> ClassificationResult:
    llm = llm or get_chat_model()
    structured = llm.with_structured_output(ClassificationResult)
    if source == "upload":
        prompt = UPLOAD_PROMPT.format(filename=filename)
    else:
        prompt = EMAIL_PROMPT.format(filename=filename, subject=subject, body=body)
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
