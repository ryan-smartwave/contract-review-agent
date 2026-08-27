from src.documents import service


def test_is_supported():
    assert service.is_supported("contract.pdf")
    assert service.is_supported("Revision (2).DOCX")
    assert not service.is_supported("photo.png")
    assert not service.is_supported("noextension")


def test_save_and_list_document():
    doc = service.save_document(b"%PDF-fake", "acme-msa.pdf", source="upload")
    assert doc.id is not None
    assert doc.mime_type == "application/pdf"
    with open(doc.file_path, "rb") as f:
        assert f.read() == b"%PDF-fake"
    assert [d.id for d in service.list_documents()] == [doc.id]


def test_init_db_creates_missing_data_dir(tmp_path, monkeypatch):
    from sqlmodel import create_engine

    from src.documents import db

    db_file = tmp_path / "nested" / "app.db"
    monkeypatch.setattr(db, "engine", create_engine(f"sqlite:///{db_file.as_posix()}"))
    db.init_db()
    assert db_file.exists()


def test_versions_auto_increment_and_latest():
    doc = service.save_document(b"x", "msa.pdf", source="upload")
    v1 = service.create_version(doc.id, "original text")
    v2 = service.create_version(doc.id, "edited text", source_suggestion_id=7)
    assert (v1.version_number, v2.version_number) == (1, 2)
    assert service.latest_version(doc.id).text_content == "edited text"
    assert [v.version_number for v in service.list_versions(doc.id)] == [1, 2]


def test_mark_review_ready_sets_timestamp():
    doc = service.save_document(b"x", "msa.pdf", source="upload")
    assert doc.review_ready_at is None
    service.mark_review_ready(doc.id)
    assert service.get_document(doc.id).review_ready_at is not None
