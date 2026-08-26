from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlmodel import select

from src.config import settings
from src.documents import db
from src.documents.models import Document, utcnow

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
