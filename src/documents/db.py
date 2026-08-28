from pathlib import Path

from contextlib import contextmanager

from sqlalchemy import text as sql_text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel, create_engine

from src.config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def init_db() -> None:
    db_path = engine.url.database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:  # additive column for pre-existing DBs
        try:
            conn.execute(sql_text("ALTER TABLE document ADD COLUMN review_ready_at TIMESTAMP"))
            conn.commit()
        except OperationalError:
            pass
        try:
            conn.execute(sql_text("ALTER TABLE documentversion ADD COLUMN file_path VARCHAR"))
            conn.commit()
        except OperationalError:
            pass
        try:
            conn.execute(sql_text("ALTER TABLE documentversion ADD COLUMN filename VARCHAR"))
            conn.commit()
        except OperationalError:
            pass


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
