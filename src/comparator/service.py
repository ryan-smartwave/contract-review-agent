import logging

from src.comparator.schemas import MatchResult
from src.documents.extract import FULL_TEXT_MAX_CHARS
from src.documents.service import latest_version, list_documents
from src.llm.factory import get_chat_model

logger = logging.getLogger(__name__)

MATCH_PROMPT = """You are matching a newly received contract against a database
of prior contracts to find the most similar one (an earlier version, the same
counterparty, or the same agreement type).

New document: {filename}
Beginning of its text:
{new_snippet}

Candidates:
{candidates}

Reply with the id of the single most similar candidate, or null if none is
plausibly related to the new document.
"""


def _candidates(document_id: int) -> list[tuple[int, str, str]]:
    """(id, filename, latest version text) for every other document with a version."""
    out = []
    for doc in list_documents():
        if doc.id == document_id:
            continue
        version = latest_version(doc.id)
        if version is None:
            continue
        out.append((doc.id, doc.filename, version.text_content))
    return out


def select_match(document_id: int, document_text: str, llm=None) -> tuple[int | None, str]:
    candidates = _candidates(document_id)
    if not candidates:
        return None, ""
    from src.documents.service import get_document

    doc = get_document(document_id)
    candidate_lines = "\n".join(
        f"- id={cid} filename={fname}\n  {text[:500]}" for cid, fname, text in candidates
    )
    llm = llm or get_chat_model()
    result: MatchResult = llm.with_structured_output(MatchResult).invoke(
        MATCH_PROMPT.format(
            filename=doc.filename if doc else "unknown",
            new_snippet=document_text[:1500],
            candidates=candidate_lines,
        )
    )
    by_id = {cid: text for cid, _, text in candidates}
    if result.matched_document_id in by_id:
        return result.matched_document_id, by_id[result.matched_document_id]
    return None, ""
