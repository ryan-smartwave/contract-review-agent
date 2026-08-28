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
        {
            "version_number": 1, "source_suggestion_id": None,
            "created_at": body["versions"][0]["created_at"], "filename": "msa.pdf",
        }
    ]
    assert body["review_seconds"] is not None and body["review_seconds"] >= 0
    created_at = body["versions"][0]["created_at"]
    assert created_at.endswith("+00:00") or created_at.endswith("Z")


def test_document_detail_versions_show_filename_for_v1_and_applied_version(client):
    from src.documents.service import create_version, mark_review_ready

    doc = save_document(b"x", "msa.pdf", source="upload")
    create_version(doc.id, "Section 2. Liability is unlimited.")
    create_version(doc.id, "Section 2. Liability is capped.", source_suggestion_id=1)
    mark_review_ready(doc.id)
    resp = client.get(f"/documents/{doc.id}")
    versions = resp.json()["versions"]
    assert versions[0]["filename"] == "msa.pdf"
    assert versions[1]["filename"] == "msa - v2.docx"


def test_document_detail_404():
    resp = TestClient(app).get("/documents/9999")
    assert resp.status_code == 404


def test_document_file_served_with_original_mime(client):
    resp = client.post("/upload", files={"file": ("nda.pdf", b"%PDF-original-bytes", "application/pdf")})
    doc_id = resp.json()["id"]
    file_resp = client.get(f"/documents/{doc_id}/file")
    assert file_resp.status_code == 200
    assert file_resp.content == b"%PDF-original-bytes"
    assert file_resp.headers["content-type"].startswith("application/pdf")


def test_document_file_404s(client):
    assert client.get("/documents/9999/file").status_code == 404


def test_version_file_v1_serves_original(client):
    from src.documents.service import create_version

    resp = client.post("/upload", files={"file": ("nda.pdf", b"%PDF-original-bytes", "application/pdf")})
    doc_id = resp.json()["id"]
    create_version(doc_id, "Section 1. Term.")
    file_resp = client.get(f"/documents/{doc_id}/versions/1/file")
    assert file_resp.status_code == 200
    assert file_resp.content == b"%PDF-original-bytes"
    assert file_resp.headers["content-type"].startswith("application/pdf")
    assert "nda.pdf" in file_resp.headers["content-disposition"]


def test_version_file_applied_version_serves_docx_with_label(client):
    from src.documents.service import create_version

    resp = client.post("/upload", files={"file": ("msa.pdf", b"%PDF-", "application/pdf")})
    doc_id = resp.json()["id"]
    create_version(doc_id, "Section 2. Liability is unlimited.")
    create_version(doc_id, "Section 2. Liability is capped.", source_suggestion_id=1)
    file_resp = client.get(f"/documents/{doc_id}/versions/2/file")
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "msa%20-%20v2.docx" in file_resp.headers["content-disposition"]


def test_version_file_unknown_version_404s(client):
    from src.documents.service import create_version

    resp = client.post("/upload", files={"file": ("nda.pdf", b"%PDF-", "application/pdf")})
    doc_id = resp.json()["id"]
    create_version(doc_id, "Section 1. Term.")
    assert client.get(f"/documents/{doc_id}/versions/99/file").status_code == 404


def test_version_file_unknown_document_404s(client):
    assert client.get("/documents/9999/versions/1/file").status_code == 404


def test_version_file_v2_without_file_path_404s(client):
    from src.documents.service import create_version

    resp = client.post("/upload", files={"file": ("nda.pdf", b"%PDF-", "application/pdf")})
    doc_id = resp.json()["id"]
    create_version(doc_id, "Section 1. Term.")  # v1
    create_version(doc_id, "Section 1. Term v2.")  # v2, no source_suggestion_id -> no file_path
    assert client.get(f"/documents/{doc_id}/versions/2/file").status_code == 404


def test_version_file_missing_from_disk_404s(client):
    from pathlib import Path

    from src.documents.service import create_version

    resp = client.post("/upload", files={"file": ("msa.pdf", b"%PDF-", "application/pdf")})
    doc_id = resp.json()["id"]
    create_version(doc_id, "Section 2. Liability is unlimited.")
    version = create_version(doc_id, "Section 2. Liability is capped.", source_suggestion_id=1)
    Path(version.file_path).unlink()
    assert client.get(f"/documents/{doc_id}/versions/2/file").status_code == 404
