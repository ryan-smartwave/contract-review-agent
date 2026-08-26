import pytest
from sqlmodel import SQLModel, create_engine

from src.documents import db


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
    )
    monkeypatch.setattr(db, "engine", engine)
    from src.config import settings
    monkeypatch.setattr(settings, "files_dir", tmp_path / "files")
    SQLModel.metadata.create_all(engine)
    yield engine
