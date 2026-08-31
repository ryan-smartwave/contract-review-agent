from dataclasses import dataclass, field

from src.documents import db
from src.documents.models import Document, DocumentVersion
from src.documents.service import create_version, latest_version
from src.reviewer.models import Suggestion


class AlreadyActionedError(Exception):
    pass


class StaleAnchorError(Exception):
    pass


def _get_pending(session, suggestion_id: int) -> Suggestion:
    suggestion = session.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise LookupError(suggestion_id)
    if suggestion.status != "pending":
        raise AlreadyActionedError(suggestion.status)
    return suggestion


def apply_suggestion(suggestion_id: int) -> DocumentVersion:
    with db.get_session() as session:
        suggestion = _get_pending(session, suggestion_id)
        version = latest_version(suggestion.document_id)
        text = version.text_content if version else ""
        if text.count(suggestion.original_text) != 1:
            suggestion.status = "stale"
            session.add(suggestion)
            session.commit()
            raise StaleAnchorError(suggestion_id)
        suggestion.status = "applied"
        session.add(suggestion)
        session.commit()
        # capture while the session is open — instances detach on exit
        document_id = suggestion.document_id
        new_text = text.replace(suggestion.original_text, suggestion.replacement_text, 1)
    try:
        return create_version(document_id, new_text, source_suggestion_id=suggestion_id)
    except Exception:
        # invariant: a suggestion is "applied" only if its version exists —
        # revert so a failed version creation leaves it retryable, not stuck.
        with db.get_session() as session:
            suggestion = session.get(Suggestion, suggestion_id)
            suggestion.status = "pending"
            session.add(suggestion)
            session.commit()
        raise


@dataclass
class BatchResult:
    version: DocumentVersion | None
    stale_ids: list[int] = field(default_factory=list)


def apply_batch(document_id: int, applied_ids: list[int], rejected_ids: list[int]) -> BatchResult:
    all_ids = [*applied_ids, *rejected_ids]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("applied_ids and rejected_ids must be disjoint and free of duplicates")
    applied: list[int] = []
    stale_ids: list[int] = []
    with db.get_session() as session:
        if session.get(Document, document_id) is None:
            raise LookupError(document_id)
        suggestions = {}
        for suggestion_id in all_ids:
            suggestion = _get_pending(session, suggestion_id)
            if suggestion.document_id != document_id:
                raise LookupError(suggestion_id)
            suggestions[suggestion_id] = suggestion
        version = latest_version(document_id)
        text = version.text_content if version else ""
        for suggestion_id in applied_ids:
            suggestion = suggestions[suggestion_id]
            if text.count(suggestion.original_text) != 1:
                suggestion.status = "stale"
                stale_ids.append(suggestion_id)
            else:
                text = text.replace(suggestion.original_text, suggestion.replacement_text, 1)
                suggestion.status = "applied"
                applied.append(suggestion_id)
        for suggestion_id in rejected_ids:
            suggestions[suggestion_id].status = "rejected"
        session.add_all(suggestions.values())
        session.commit()
    if not applied:
        return BatchResult(version=None, stale_ids=stale_ids)
    try:
        new_version = create_version(document_id, text, render_file=True)
    except Exception:
        # invariant: a batch's statuses stand only if its version exists — revert
        # everything (stale marks were computed against text that now never
        # existed) so the identical confirm is retryable, not stuck.
        with db.get_session() as session:
            for suggestion_id in all_ids:
                suggestion = session.get(Suggestion, suggestion_id)
                suggestion.status = "pending"
                session.add(suggestion)
            session.commit()
        raise
    return BatchResult(version=new_version, stale_ids=stale_ids)


def reject_suggestion(suggestion_id: int) -> Suggestion:
    with db.get_session() as session:
        suggestion = _get_pending(session, suggestion_id)
        suggestion.status = "rejected"
        session.add(suggestion)
        session.commit()
        session.refresh(suggestion)
    return suggestion
