from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlmodel import select

from src.config import settings
from src.documents import db
from src.documents.models import Document, DocumentVersion, utcnow
from src.documents.render import render_docx

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def is_supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS


def save_document(
    content: bytes, filename: str, source: str, detected_at: datetime | None = None
) -> Document:
    ext = Path(filename).suffix.lower()
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    file_path = settings.files_dir / f"{uuid4().hex}{ext}"
    file_path.write_bytes(content)
    doc = Document(
        filename=filename,
        file_path=str(file_path),
        source=source,
        mime_type=MIME_TYPES[ext],
        detected_at=detected_at or utcnow(),
    )
    with db.get_session() as session:
        session.add(doc)
        session.commit()
        session.refresh(doc)
    return doc


def list_documents() -> list[Document]:
    with db.get_session() as session:
        return list(session.exec(select(Document).order_by(Document.detected_at.desc())))


def delete_document(doc: Document) -> None:
    Path(doc.file_path).unlink(missing_ok=True)
    with db.get_session() as session:
        session.delete(session.get(Document, doc.id))
        session.commit()


def create_version(
    document_id: int, text_content: str, source_suggestion_id: int | None = None
) -> DocumentVersion:
    with db.get_session() as session:
        current = session.exec(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        ).first()
        version_number = (current.version_number + 1) if current else 1
        version = DocumentVersion(
            document_id=document_id,
            version_number=version_number,
            text_content=text_content,
            source_suggestion_id=source_suggestion_id,
        )
        if source_suggestion_id is not None:
            doc = session.get(Document, document_id)
            label = f"{Path(doc.filename).stem} - v{version_number}.docx"
            settings.files_dir.mkdir(parents=True, exist_ok=True)
            file_path = settings.files_dir / f"{uuid4().hex}.docx"
            file_path.write_bytes(render_docx(text_content))
            version.file_path = str(file_path)
            version.filename = label
        session.add(version)
        session.commit()
        session.refresh(version)
    return version


def latest_version(document_id: int) -> DocumentVersion | None:
    with db.get_session() as session:
        return session.exec(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        ).first()


def list_versions(document_id: int) -> list[DocumentVersion]:
    with db.get_session() as session:
        return list(session.exec(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number)
        ))


def get_document(document_id: int) -> Document | None:
    with db.get_session() as session:
        return session.get(Document, document_id)


def mark_review_ready(document_id: int) -> None:
    with db.get_session() as session:
        doc = session.get(Document, document_id)
        doc.review_ready_at = utcnow()
        session.add(doc)
        session.commit()
