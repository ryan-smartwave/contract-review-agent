import logging

from src.comparator.schemas import MatchResult
from src.documents.extract import FULL_TEXT_MAX_CHARS
from src.documents.service import get_document, latest_version, list_documents
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


from sqlmodel import select

from src.comparator.models import Comparison, ComparisonChange
from src.comparator.schemas import ChangeDraft, CompareResult
from src.documents import db

COMPARE_PROMPT = """You are comparing a newly received contract against the most
similar prior contract from our database. Identify what changed.

For each change:
- kind: "added" (new clause/text), "removed" (present before, gone now), or
  "modified" (present in both, altered).
- clause: a short human label (e.g. "Section 4 - Liability").
- before_text: an EXACT, VERBATIM excerpt from the PRIOR contract (required for
  removed and modified; null for added). It must appear exactly once in the
  prior contract, must not span a blank line, and must stay under 300 characters.
- after_text: an EXACT, VERBATIM excerpt from the NEW contract (required for
  added and modified; null for removed). Same rules against the new contract.
- note: one sentence on what the change does.

Also write a 2-4 sentence summary of the overall differences.

PRIOR contract:
{old_text}

NEW contract:
{new_text}
"""


def _anchored(change: ChangeDraft, new_text: str, old_text: str) -> bool:
    needs_after = change.kind in ("added", "modified")
    needs_before = change.kind in ("removed", "modified")
    if needs_after and not (change.after_text and new_text.count(change.after_text) == 1):
        return False
    if needs_before and not (change.before_text and old_text.count(change.before_text) == 1):
        return False
    return True


def _store(document_id: int, status: str, matched_document_id: int | None = None,
           summary: str | None = None, changes: list[ChangeDraft] | None = None) -> Comparison:
    with db.get_session() as session:
        comparison = Comparison(
            document_id=document_id, matched_document_id=matched_document_id,
            status=status, summary=summary,
        )
        session.add(comparison)
        session.commit()
        session.refresh(comparison)
        for change in changes or []:
            session.add(ComparisonChange(comparison_id=comparison.id, **change.model_dump()))
        session.commit()
        session.refresh(comparison)
    return comparison


def run_comparison(document_id: int, document_text: str, llm=None) -> Comparison:
    try:
        matched_id, old_text = select_match(document_id, document_text, llm=llm)
        if matched_id is None:
            return _store(document_id, "no_match")
        new_text = document_text[:FULL_TEXT_MAX_CHARS]
        old_text = old_text[:FULL_TEXT_MAX_CHARS]
        model = llm or get_chat_model()
        result: CompareResult = model.with_structured_output(CompareResult).invoke(
            COMPARE_PROMPT.format(old_text=old_text, new_text=new_text)
        )
        kept = [c for c in result.changes if _anchored(c, new_text, old_text)]
        return _store(document_id, "ready", matched_document_id=matched_id,
                      summary=result.summary, changes=kept)
    except Exception:
        logger.exception("comparison failed for document %s", document_id)
        return _store(document_id, "failed")


def get_comparison(document_id: int) -> tuple[Comparison, list[ComparisonChange]] | None:
    with db.get_session() as session:
        comparison = session.exec(
            select(Comparison)
            .where(Comparison.document_id == document_id)
            .order_by(Comparison.id.desc())
        ).first()
        if comparison is None:
            return None
        changes = list(session.exec(
            select(ComparisonChange)
            .where(ComparisonChange.comparison_id == comparison.id)
            .order_by(ComparisonChange.id)
        ))
    return comparison, changes
