import pytest
from fastapi.testclient import TestClient

from src.documents import db
from src.documents.service import create_version, latest_version, list_versions, save_document
from src.main import app
from src.redliner import service
from src.reviewer.models import Suggestion

TEXT = "A. Term is 12 months. B. Liability is unlimited. C. Venue is Manila."


def _suggestion(doc_id, original, replacement):
    s = Suggestion(document_id=doc_id, clause="c", original_text=original,
                   replacement_text=replacement, rationale="r")
    with db.get_session() as session:
        session.add(s)
        session.commit()
        session.refresh(s)
    return s


def _doc_with_text():
    doc = save_document(b"x", "msa.pdf", source="upload")
    create_version(doc.id, TEXT)
    return doc


def test_apply_creates_new_version_and_marks_applied():
    doc = _doc_with_text()
    s = _suggestion(doc.id, "Liability is unlimited.", "Liability is capped at fees.")
    version = service.apply_suggestion(s.id)
    assert version.version_number == 2
    assert "Liability is capped at fees." in version.text_content
    assert "Liability is unlimited." not in version.text_content
    assert version.source_suggestion_id == s.id


def test_sequential_applies_and_reject_are_independent():
    doc = _doc_with_text()
    s1 = _suggestion(doc.id, "Term is 12 months.", "Term is 24 months.")
    s2 = _suggestion(doc.id, "Venue is Manila.", "Venue is Singapore.")
    s3 = _suggestion(doc.id, "A. ", "A) ")
    service.apply_suggestion(s1.id)
    service.apply_suggestion(s2.id)
    final = latest_version(doc.id).text_content
    assert "Term is 24 months." in final and "Venue is Singapore." in final
    rejected = service.reject_suggestion(s3.id)
    assert rejected.status == "rejected"
    assert len(list_versions(doc.id)) == 3  # v1 + two applies, reject adds none


def test_stale_anchor_marks_stale_and_raises():
    doc = _doc_with_text()
    s1 = _suggestion(doc.id, "B. Liability is unlimited.", "B. Liability is capped.")
    s2 = _suggestion(doc.id, "Liability is unlimited.", "conflicting change")
    service.apply_suggestion(s1.id)
    with pytest.raises(service.StaleAnchorError):
        service.apply_suggestion(s2.id)
    with db.get_session() as session:
        assert session.get(Suggestion, s2.id).status == "stale"


def test_already_actioned_raises():
    doc = _doc_with_text()
    s = _suggestion(doc.id, "Venue is Manila.", "Venue is Singapore.")
    service.reject_suggestion(s.id)
    with pytest.raises(service.AlreadyActionedError):
        service.apply_suggestion(s.id)


def test_apply_endpoint_returns_detail_and_409s():
    client = TestClient(app)
    doc = _doc_with_text()
    s = _suggestion(doc.id, "Venue is Manila.", "Venue is Singapore.")
    resp = client.post(f"/suggestions/{s.id}/apply")
    assert resp.status_code == 200
    body = resp.json()
    assert "Venue is Singapore." in body["text"]
    assert body["suggestions"][0]["status"] == "applied"
    resp2 = client.post(f"/suggestions/{s.id}/apply")
    assert resp2.status_code == 409
    assert client.post("/suggestions/99999/reject").status_code == 404
