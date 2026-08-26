import pytest
from fastapi.testclient import TestClient

from src.classifier.schemas import ClassificationResult
from src.intake import router as intake_router
from src.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        intake_router, "classify_and_log",
        lambda document_id, filename, **kw: ClassificationResult(
            is_contract_revision=True, confidence=0.9, reasoning="stub"),
    )
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
