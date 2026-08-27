from fastapi import APIRouter, HTTPException

from src.documents import db
from src.documents.schemas import DocumentDetailOut, document_detail
from src.redliner.service import (
    AlreadyActionedError,
    StaleAnchorError,
    apply_suggestion,
    reject_suggestion,
)
from src.reviewer.models import Suggestion

router = APIRouter()


def _detail_for(suggestion_id: int) -> DocumentDetailOut:
    with db.get_session() as session:
        suggestion = session.get(Suggestion, suggestion_id)
    return document_detail(suggestion.document_id)


@router.post("/suggestions/{suggestion_id}/apply")
def apply(suggestion_id: int) -> DocumentDetailOut:
    try:
        apply_suggestion(suggestion_id)
    except LookupError:
        raise HTTPException(404, "Suggestion not found")
    except AlreadyActionedError as exc:
        raise HTTPException(409, f"Suggestion already {exc}")
    except StaleAnchorError:
        raise HTTPException(
            409, "This suggestion's text was changed by an earlier applied edit; it is now stale."
        )
    return _detail_for(suggestion_id)


@router.post("/suggestions/{suggestion_id}/reject")
def reject(suggestion_id: int) -> DocumentDetailOut:
    try:
        reject_suggestion(suggestion_id)
    except LookupError:
        raise HTTPException(404, "Suggestion not found")
    except AlreadyActionedError as exc:
        raise HTTPException(409, f"Suggestion already {exc}")
    return _detail_for(suggestion_id)
