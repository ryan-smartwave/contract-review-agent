import pytest
from fastapi.testclient import TestClient

from src.classifier.schemas import ClassificationResult
from src.intake import pipeline
from src.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        pipeline, "classify_and_log",
        lambda document_id, filename, **kw: ClassificationResult(
            is_contract_revision=True, confidence=0.9, reasoning="stub"),
    )
    monkeypatch.setattr(pipeline, "run_review", lambda *a, **kw: [])
    return TestClient(app)


def test_upload_pdf_returns_document_with_classification(client):
    resp = client.post("/upload", files={"file": ("nda.pdf", b"%PDF-", "application/pdf")})
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "nda.pdf"
    assert body["source"] == "upload"
    assert body["is_contract_revision"] is True


def test_upload_unsupported_type_rejected(client):
    resp = client.post("/upload", files={"file": ("cat.gif", b"GIF89a", "image/gif")})
    assert resp.status_code == 422
    assert "PDF or DOCX" in resp.json()["detail"]


def test_documents_list_includes_upload(client):
    client.post("/upload", files={"file": ("nda.pdf", b"%PDF-", "application/pdf")})
    resp = client.get("/documents")
    assert resp.status_code == 200
    assert [d["filename"] for d in resp.json()] == ["nda.pdf"]


def test_document_detected_at_is_serialized_as_utc(client):
    client.post("/upload", files={"file": ("nda.pdf", b"%PDF-", "application/pdf")})
    resp = client.get("/documents")
    detected_at = resp.json()[0]["detected_at"]
    assert detected_at.endswith("+00:00") or detected_at.endswith("Z")


def test_upload_rolls_back_when_classification_fails(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(pipeline, "classify_and_log", boom)
    resp = client.post("/upload", files={"file": ("nda.pdf", b"%PDF-", "application/pdf")})
    assert resp.status_code == 502
    assert "classification failed" in resp.json()["detail"]
    assert client.get("/documents").json() == []


from src.classifier.schemas import ClassificationResult
from src.documents.service import save_document
from src.reviewer.models import Suggestion
from src.reviewer import service as reviewer_service


def test_upload_triggers_review_when_contract_revision(client, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run_review", lambda doc_id, text, **kw: calls.append((doc_id, text)))
    client.post("/upload", files={"file": ("nda.pdf", b"%PDF-", "application/pdf")})
    assert len(calls) == 1


def test_document_detail_returns_text_suggestions_versions(client):
    from src.documents.service import create_version, mark_review_ready
    from src.documents import db as ddb

    doc = save_document(b"x", "msa.pdf", source="upload")
    create_version(doc.id, "Section 2. Liability is unlimited.")
    with ddb.get_session() as session:
        session.add(Suggestion(
            document_id=doc.id, clause="Section 2",
            original_text="Liability is unlimited.",
            replacement_text="Liability is capped.", rationale="risk",
        ))
        session.commit()
    mark_review_ready(doc.id)
    resp = client.get(f"/documents/{doc.id}")
    body = resp.json()
    assert resp.status_code == 200
    assert body["text"] == "Section 2. Liability is unlimited."
    assert body["suggestions"][0]["status"] == "pending"
    assert body["versions"] == [
        {"version_number": 1, "source_suggestion_id": None, "created_at": body["versions"][0]["created_at"]}
    ]
    assert body["review_seconds"] is not None and body["review_seconds"] >= 0


def test_document_detail_404():
    resp = TestClient(app).get("/documents/9999")
    assert resp.status_code == 404
