from io import BytesIO

from docx import Document

from src.documents import db
from src.documents.service import create_version, save_document
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
    doc = save_document(b"original-bytes", "msa.pdf", source="upload")
    create_version(doc.id, TEXT)
    return doc


def test_apply_suggestion_writes_labeled_version_file():
    doc = _doc_with_text()
    s = _suggestion(doc.id, "Liability is unlimited.", "Liability is capped at fees.")

    version = service.apply_suggestion(s.id)

    assert version.filename == "msa - v2.docx"
    assert version.file_path is not None
    with open(version.file_path, "rb") as f:
        data = f.read()
    docx_doc = Document(BytesIO(data))
    joined = "\n".join(p.text for p in docx_doc.paragraphs)
    assert "Liability is capped at fees." in joined

    # original document file is untouched
    with open(doc.file_path, "rb") as f:
        assert f.read() == b"original-bytes"


def test_first_version_has_no_file():
    doc = _doc_with_text()
    first = create_version(doc.id, "more text", source_suggestion_id=None)
    assert first.file_path is None
    assert first.filename is None
