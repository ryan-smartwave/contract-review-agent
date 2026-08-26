from sqlmodel import select

from src.classifier.models import ClassificationLog
from src.classifier.schemas import ClassificationResult
from src.documents import db
from src.llm.factory import get_chat_model

PROMPT = """You are a legal-operations email triage assistant.
Decide whether this email + attachment is a CONTRACT REVISION \
(a new draft, redline, or amendment of a contract) or not \
(invoice, newsletter, receipt, general correspondence, etc.).

Attachment filename: {filename}
Email subject: {subject}
Email body (may be empty): {body}
"""


def classify_and_log(
    document_id: int, filename: str, subject: str = "", body: str = "", llm=None
) -> ClassificationResult:
    llm = llm or get_chat_model()
    structured = llm.with_structured_output(ClassificationResult)
    result = structured.invoke(PROMPT.format(filename=filename, subject=subject, body=body))
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
