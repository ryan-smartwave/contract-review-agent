from src.documents import db
from src.documents.models import DocumentVersion
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


def reject_suggestion(suggestion_id: int) -> Suggestion:
    with db.get_session() as session:
        suggestion = _get_pending(session, suggestion_id)
        suggestion.status = "rejected"
        session.add(suggestion)
        session.commit()
        session.refresh(suggestion)
    return suggestion
