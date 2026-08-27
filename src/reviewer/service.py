from sqlmodel import select

from src.documents import db
from src.documents.service import create_version, latest_version, mark_review_ready
from src.llm.factory import get_chat_model
from src.reviewer.models import Suggestion
from src.reviewer.schemas import ReviewResult

REVIEW_PROMPT = """You are a contract review assistant for a legal-operations team.
Review the contract text below and propose specific redlines that protect our side:
liability caps, termination rights, payment terms, confidentiality, governing law,
ambiguous obligations. Propose only changes that matter.

For each suggestion:
- clause: a short human label for where the change applies (e.g. "Section 2 - Liability").
- original_text: an EXACT, VERBATIM excerpt copied from the contract text that should
  be replaced. It must appear exactly once in the document. Keep it under 300 characters.
- replacement_text: the full replacement for that excerpt.
- rationale: one or two sentences on why.

Contract text:
{document_text}
"""


def run_review(document_id: int, document_text: str, llm=None) -> list[Suggestion]:
    if latest_version(document_id) is None:
        create_version(document_id, document_text)
    llm = llm or get_chat_model()
    result: ReviewResult = llm.with_structured_output(ReviewResult).invoke(
        REVIEW_PROMPT.format(document_text=document_text)
    )
    kept = [d for d in result.suggestions if document_text.count(d.original_text) == 1]
    suggestions = [Suggestion(document_id=document_id, **d.model_dump()) for d in kept]
    with db.get_session() as session:
        for suggestion in suggestions:
            session.add(suggestion)
        session.commit()
        for suggestion in suggestions:
            session.refresh(suggestion)
    mark_review_ready(document_id)
    return suggestions


def list_suggestions(document_id: int) -> list[Suggestion]:
    with db.get_session() as session:
        return list(session.exec(
            select(Suggestion)
            .where(Suggestion.document_id == document_id)
            .order_by(Suggestion.id)
        ))
