# Contract Review Agent — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship tracker rows 1–4 and 6 by Friday 2026-08-28: Gmail inbox monitoring, contract-revision classification, manual upload, Drive search, and a web UI (with Globe-suitable design system) that displays results.

**Architecture:** Multi-repo. This repo (`contract-review-agent`) is the Python backend: FastAPI + capability domain modules (`intake`, `classifier`, `locator`, `documents`, `llm`), each a package with its own `service.py`/`router.py`/`schemas.py`/`models.py` — the future A2A sub-agent seams. A sibling repo `contract-review-web` (Next.js, bulletproof-react layout) hosts the UI. All model calls go through LangChain `init_chat_model` — no vendor SDK imports anywhere.

**Tech Stack:** Python 3.12, FastAPI, SQLModel (SQLite), LangChain (`init_chat_model`), google-api-python-client, pytest. Web: Next.js 15 (App Router, TypeScript), Tailwind CSS v4, Vitest + React Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-26-contract-review-agent-design.md`

## Global Constraints

- **No vendor AI SDK imports** — model access only via `langchain.chat_models.init_chat_model`; provider comes from `MODEL_NAME` config (e.g. `anthropic:claude-sonnet-4-5`, `openai:gpt-4o`).
- **Supported document types:** `.pdf`, `.docx` only. Everything else ignored/rejected gracefully — never an error for non-document emails.
- **Coding principles (CLAUDE.md):** DRY, KISS, self-documenting code, YAGNI. No A2A endpoint in this phase (Phase 2); no gateway work at all (per Juls).
- **Design system:** all colors/typography via CSS custom properties in one tokens file — Globe-inspired placeholder palette, swappable when official brand guidelines arrive. Never hardcode a hex in a component.
- **Web import rule (bulletproof-react):** shared (`components/`, `lib/`) → `features/*` → `app/`. Features never import from other features or from `app/`.
- Backend commands run from repo root `D:\SmartWave\contract-review-agent`; web commands from `D:\SmartWave\contract-review-web`. Windows/PowerShell environment.

---

### Task 1: Backend scaffold

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/__init__.py`, `src/config.py`, `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `src.config.settings` — a `Settings` object with fields `model_name: str`, `database_url: str`, `files_dir: Path`, `google_credentials_path: Path`, `google_token_path: Path`, `gmail_poll_seconds: int`, `enable_gmail_poller: bool`. All later tasks import `from src.config import settings`.

- [ ] **Step 1: Write project metadata and gitignore**

`pyproject.toml`:

```toml
[project]
name = "contract-review-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlmodel>=0.0.22",
    "pydantic-settings>=2.4",
    "langchain>=0.3",
    "langchain-anthropic>=0.2",
    "langchain-openai>=0.2",
    "google-api-python-client>=2.140",
    "google-auth-oauthlib>=1.2",
    "python-multipart>=0.0.9",
]

[dependency-groups]
dev = ["pytest>=8.3", "httpx>=0.27"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:

```
.venv/
__pycache__/
data/
.env
credentials.json
token.json
```

`.env.example`:

```
MODEL_NAME=anthropic:claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-...
ENABLE_GMAIL_POLLER=false
```

- [ ] **Step 2: Create venv and install**

Run:

```powershell
py -3.12 -m venv .venv; .venv\Scripts\pip install -e . --group dev
```

Expected: install succeeds. (If `--group` unsupported by pip version: `.venv\Scripts\pip install -e . pytest httpx`.)

- [ ] **Step 3: Write the failing config test**

`tests/test_config.py`:

```python
from pathlib import Path

from src.config import settings


def test_settings_defaults():
    assert settings.model_name.count(":") == 1  # "provider:model" form
    assert settings.files_dir == Path("data/files")
    assert settings.gmail_poll_seconds == 30
    assert settings.enable_gmail_poller is False
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 5: Write src/config.py**

```python
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_name: str = "anthropic:claude-sonnet-4-5"
    database_url: str = "sqlite:///data/app.db"
    files_dir: Path = Path("data/files")
    google_credentials_path: Path = Path("credentials.json")
    google_token_path: Path = Path("token.json")
    gmail_poll_seconds: int = 30
    enable_gmail_poller: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
```

Create empty `src/__init__.py` and `tests/__init__.py`.

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv\Scripts\pytest tests/test_config.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .env.example src tests
git commit -m "feat: backend scaffold with typed settings"
```

---

### Task 2: Google Cloud OAuth setup

**Files:**
- Create: `scripts/google_auth.py`, `docs/google-setup.md`

**Interfaces:**
- Produces: `token.json` at repo root (gitignored) holding user OAuth credentials with Gmail + Drive scopes; `scripts/google_auth.py get_credentials() -> Credentials` reused by Tasks 8 and 9. Scope constants `SCOPES = ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/drive.readonly"]`.

This task is part manual (Google Cloud console) and part scripted. It has no unit test; verification is the script printing the authorized email. **Do the manual part first thing — it gates Tasks 8 and 9.**

- [ ] **Step 1: Manual console setup — document as you go**

In https://console.cloud.google.com with the demo Google account:
1. Create project `contract-review-demo`.
2. Enable **Gmail API** and **Google Drive API** (APIs & Services → Library).
3. OAuth consent screen: External, app name `Contract Review Agent`, add the demo account as a test user.
4. Credentials → Create Credentials → OAuth client ID → **Desktop app** → download JSON as `credentials.json` in repo root.

Record each step (with the project id and demo account used) in `docs/google-setup.md` so JC/Eris can reproduce it.

- [ ] **Step 2: Write scripts/google_auth.py**

```python
"""One-time OAuth flow; later runs reuse token.json silently."""
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
]


def get_credentials() -> Credentials:
    creds = None
    if settings.google_token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(settings.google_token_path), SCOPES
        )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(settings.google_credentials_path), SCOPES
        )
        creds = flow.run_local_server(port=0)
    settings.google_token_path.write_text(creds.to_json())
    return creds


if __name__ == "__main__":
    from googleapiclient.discovery import build

    creds = get_credentials()
    profile = build("gmail", "v1", credentials=creds).users().getProfile(userId="me").execute()
    print(f"Authorized as: {profile['emailAddress']}")
```

- [ ] **Step 3: Run the flow and verify**

Run: `.venv\Scripts\python -m scripts.google_auth` (add empty `scripts/__init__.py`)
Expected: browser opens, consent granted, terminal prints `Authorized as: <demo account email>`; `token.json` exists.

- [ ] **Step 4: Commit (script and doc only — never credentials)**

```bash
git add scripts docs/google-setup.md
git commit -m "feat: google oauth flow for gmail and drive scopes"
```

---

### Task 3: Vendor-agnostic LLM factory

**Files:**
- Create: `src/llm/__init__.py`, `src/llm/factory.py`, `tests/test_llm_factory.py`

**Interfaces:**
- Produces: `src.llm.factory.get_chat_model()` → a LangChain chat model built from `settings.model_name`. Consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

`tests/test_llm_factory.py`:

```python
import subprocess

from src.llm import factory


def test_get_chat_model_uses_configured_name(monkeypatch):
    captured = {}

    def fake_init(model, **kwargs):
        captured["model"] = model
        return object()

    monkeypatch.setattr(factory, "init_chat_model", fake_init)
    factory.get_chat_model()
    assert captured["model"] == factory.settings.model_name


def test_no_vendor_sdk_imports():
    # AI abstraction constraint: no direct anthropic/openai imports in src/
    grep = subprocess.run(
        ["git", "grep", "-lE", r"^(import|from) (anthropic|openai)", "--", "src/"],
        capture_output=True, text=True,
    )
    assert grep.stdout == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_llm_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.llm'`

- [ ] **Step 3: Write src/llm/factory.py**

```python
from langchain.chat_models import init_chat_model

from src.config import settings


def get_chat_model():
    return init_chat_model(settings.model_name)
```

Create empty `src/llm/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_llm_factory.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/llm tests/test_llm_factory.py
git commit -m "feat: vendor-agnostic llm factory via init_chat_model"
```

---

### Task 4: Documents module (storage + supported types)

**Files:**
- Create: `src/documents/__init__.py`, `src/documents/db.py`, `src/documents/models.py`, `src/documents/service.py`, `tests/test_documents.py`, `tests/conftest.py`

**Interfaces:**
- Produces:
  - `Document(SQLModel)`: `id: int | None`, `filename: str`, `file_path: str`, `source: str` (`"email"` or `"upload"`), `mime_type: str`, `detected_at: datetime`, `created_at: datetime`.
  - `service.is_supported(filename: str) -> bool` and `service.SUPPORTED_EXTENSIONS: set[str]`.
  - `service.save_document(content: bytes, filename: str, source: str, detected_at: datetime | None = None) -> Document`
  - `service.list_documents() -> list[Document]`
  - `db.init_db()`, `db.get_session()` (contextmanager yielding a `Session`).
- Consumed by: Tasks 5, 6, 7, 8.

- [ ] **Step 1: Write the failing tests**

`tests/conftest.py` (shared in-memory DB + tmp files for all backend tests):

```python
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
```

`tests/test_documents.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_documents.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.documents'`

- [ ] **Step 3: Implement the module**

`src/documents/db.py`:

```python
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from src.config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
```

`src/documents/models.py`:

```python
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str
    file_path: str
    source: str  # "email" | "upload"
    mime_type: str
    detected_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
```

`src/documents/service.py`:

```python
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
```

Create empty `src/documents/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_documents.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/documents tests/test_documents.py tests/conftest.py
git commit -m "feat: documents module with sqlite storage and supported-type check"
```

---

### Task 5: Classifier module

**Files:**
- Create: `src/classifier/__init__.py`, `src/classifier/schemas.py`, `src/classifier/models.py`, `src/classifier/service.py`, `tests/test_classifier.py`

**Interfaces:**
- Consumes: `get_chat_model()` (Task 3), `db.get_session()` (Task 4).
- Produces:
  - `ClassificationResult(BaseModel)`: `is_contract_revision: bool`, `confidence: float`, `reasoning: str`.
  - `ClassificationLog(SQLModel)`: `id`, `document_id: int`, `is_contract_revision: bool`, `confidence: float`, `reasoning: str`, `created_at: datetime`.
  - `service.classify_and_log(document_id: int, filename: str, subject: str = "", body: str = "", llm=None) -> ClassificationResult` — classifies and persists a log row. `llm` is injectable for tests; defaults to `get_chat_model()`.
  - `service.get_log(document_id: int) -> ClassificationLog | None`.
- Consumed by: Tasks 6 and 7.

- [ ] **Step 1: Write the failing tests**

`tests/test_classifier.py`:

```python
from src.classifier import service
from src.classifier.schemas import ClassificationResult
from src.documents.service import save_document


class FakeStructuredLLM:
    def __init__(self, result):
        self.result = result
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.result


def test_classify_and_log_persists_decision():
    doc = save_document(b"x", "msa-v2.docx", source="email")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=True, confidence=0.93,
        reasoning="Subject mentions redlined MSA revision.",
    ))
    result = service.classify_and_log(
        doc.id, doc.filename, subject="Re: MSA v2 redlines", body="see attached", llm=fake,
    )
    assert result.is_contract_revision is True
    log = service.get_log(doc.id)
    assert log is not None and log.confidence == 0.93
    assert "msa-v2.docx" in fake.prompts[0]


def test_classify_negative_case():
    doc = save_document(b"x", "newsletter.pdf", source="email")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=False, confidence=0.98, reasoning="Marketing newsletter.",
    ))
    result = service.classify_and_log(doc.id, doc.filename, subject="August deals!", llm=fake)
    assert result.is_contract_revision is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_classifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.classifier'`

- [ ] **Step 3: Implement the module**

`src/classifier/schemas.py`:

```python
from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    is_contract_revision: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
```

`src/classifier/models.py`:

```python
from datetime import datetime

from sqlmodel import Field, SQLModel

from src.documents.models import utcnow


class ClassificationLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    is_contract_revision: bool
    confidence: float
    reasoning: str
    created_at: datetime = Field(default_factory=utcnow)
```

`src/classifier/service.py`:

```python
from sqlmodel import select

from src.classifier.models import ClassificationLog
from src.classifier.schemas import ClassificationResult
from src.documents import db
from src.llm.factory import get_chat_model

PROMPT = """You are a legal-operations email triage assistant.
Decide whether this email + attachment is a CONTRACT REVISION \
(a new draft, redline, or amendment of a contract) or not \
(invoice, newsletter, receipt, general correspondence, etc.).

Attachment filename: {filename}
Email subject: {subject}
Email body (may be empty): {body}
"""


def classify_and_log(
    document_id: int, filename: str, subject: str = "", body: str = "", llm=None
) -> ClassificationResult:
    llm = llm or get_chat_model()
    structured = llm.with_structured_output(ClassificationResult)
    result = structured.invoke(PROMPT.format(filename=filename, subject=subject, body=body))
    with db.get_session() as session:
        session.add(ClassificationLog(document_id=document_id, **result.model_dump()))
        session.commit()
    return result


def get_log(document_id: int) -> ClassificationLog | None:
    with db.get_session() as session:
        return session.exec(
            select(ClassificationLog)
            .where(ClassificationLog.document_id == document_id)
            .order_by(ClassificationLog.created_at.desc())
        ).first()
```

Create empty `src/classifier/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_classifier.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/classifier tests/test_classifier.py
git commit -m "feat: llm contract-revision classifier with persisted decision log"
```

---

### Task 6: FastAPI app — upload endpoint + documents list

**Files:**
- Create: `src/main.py`, `src/intake/__init__.py`, `src/intake/router.py`, `src/documents/router.py`, `src/documents/schemas.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `save_document`, `is_supported`, `list_documents` (Task 4); `classify_and_log`, `get_log` (Task 5).
- Produces:
  - `POST /upload` (multipart `file`) → 201 `DocumentOut`; 422 for unsupported types with `{"detail": "Unsupported file type. Upload a PDF or DOCX."}`.
  - `GET /documents` → `list[DocumentOut]`.
  - `DocumentOut(BaseModel)`: `id: int`, `filename: str`, `source: str`, `mime_type: str`, `detected_at: datetime`, `is_contract_revision: bool | None`, `confidence: float | None`, `reasoning: str | None`.
  - `src.main.app` — FastAPI instance with CORS for `http://localhost:3000`. Consumed by Tasks 8, 9 and the web repo.

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.main'`

- [ ] **Step 3: Implement schemas, routers, app**

`src/documents/schemas.py`:

```python
from datetime import datetime

from pydantic import BaseModel

from src.classifier.models import ClassificationLog
from src.documents.models import Document


class DocumentOut(BaseModel):
    id: int
    filename: str
    source: str
    mime_type: str
    detected_at: datetime
    is_contract_revision: bool | None = None
    confidence: float | None = None
    reasoning: str | None = None

    @classmethod
    def from_document(cls, doc: Document, log: ClassificationLog | None) -> "DocumentOut":
        return cls(
            id=doc.id, filename=doc.filename, source=doc.source,
            mime_type=doc.mime_type, detected_at=doc.detected_at,
            is_contract_revision=log.is_contract_revision if log else None,
            confidence=log.confidence if log else None,
            reasoning=log.reasoning if log else None,
        )
```

`src/intake/router.py`:

```python
from fastapi import APIRouter, HTTPException, UploadFile

from src.classifier.service import classify_and_log, get_log
from src.documents.schemas import DocumentOut
from src.documents.service import is_supported, save_document

router = APIRouter()


@router.post("/upload", status_code=201)
async def upload(file: UploadFile) -> DocumentOut:
    if not is_supported(file.filename or ""):
        raise HTTPException(422, "Unsupported file type. Upload a PDF or DOCX.")
    doc = save_document(await file.read(), file.filename, source="upload")
    classify_and_log(doc.id, doc.filename)
    return DocumentOut.from_document(doc, get_log(doc.id))
```

`src/documents/router.py`:

```python
from fastapi import APIRouter

from src.classifier.service import get_log
from src.documents.schemas import DocumentOut
from src.documents.service import list_documents

router = APIRouter()


@router.get("/documents")
def documents() -> list[DocumentOut]:
    return [DocumentOut.from_document(d, get_log(d.id)) for d in list_documents()]
```

`src/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.documents import router as documents_router
from src.documents.db import init_db
from src.intake import router as intake_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Contract Review Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(intake_router.router)
app.include_router(documents_router.router)
```

- [ ] **Step 4: Run all tests**

Run: `.venv\Scripts\pytest -v`
Expected: PASS (all tests so far)

- [ ] **Step 5: Smoke-run the server**

Run: `.venv\Scripts\uvicorn src.main:app --port 8000` then open http://localhost:8000/docs
Expected: Swagger UI shows `/upload` and `/documents`. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add src/main.py src/intake src/documents tests/test_api.py
git commit -m "feat: upload endpoint and documents list api (tracker row 3)"
```

---

### Task 7: Gmail intake service (row 1 + 2 pipeline)

**Files:**
- Create: `src/intake/gmail_client.py`, `src/intake/service.py`, `tests/test_intake.py`

**Interfaces:**
- Consumes: `save_document`, `is_supported` (Task 4); `classify_and_log` (Task 5).
- Produces:
  - `Attachment` dataclass: `filename: str`, `content: bytes`.
  - `EmailMessage` dataclass: `message_id: str`, `subject: str`, `body: str`, `received_at: datetime`, `attachments: list[Attachment]`.
  - `GmailClientProtocol`: `fetch_unread_with_attachments() -> list[EmailMessage]`, `mark_processed(message_id: str) -> None`.
  - `service.process_inbox(client) -> list[Document]` — saves+classifies every supported attachment, marks every fetched message processed, silently skips unsupported/no-attachment messages.
- Consumed by: Task 8 (poller uses `process_inbox` with the real client).

- [ ] **Step 1: Write the failing tests**

`tests/test_intake.py`:

```python
from datetime import datetime, timezone

from src.classifier.schemas import ClassificationResult
from src.intake import service
from src.intake.gmail_client import Attachment, EmailMessage


class FakeGmail:
    def __init__(self, messages):
        self.messages = messages
        self.processed = []

    def fetch_unread_with_attachments(self):
        return self.messages

    def mark_processed(self, message_id):
        self.processed.append(message_id)


def _msg(mid, subject, attachments):
    return EmailMessage(
        message_id=mid, subject=subject, body="",
        received_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        attachments=attachments,
    )


def test_process_inbox_saves_supported_attachments(monkeypatch):
    monkeypatch.setattr(
        service, "classify_and_log",
        lambda document_id, filename, **kw: ClassificationResult(
            is_contract_revision=True, confidence=0.9, reasoning="stub"),
    )
    fake = FakeGmail([
        _msg("m1", "MSA v2 redline", [Attachment("msa-v2.docx", b"docx")]),
        _msg("m2", "Team photo", [Attachment("photo.png", b"png")]),
    ])
    docs = service.process_inbox(fake)
    assert [d.filename for d in docs] == ["msa-v2.docx"]
    assert docs[0].source == "email"
    assert docs[0].detected_at.year == 2026  # detected_at = email received time
    assert fake.processed == ["m1", "m2"]  # both marked, no error on m2


def test_process_inbox_empty_inbox_is_noop():
    assert service.process_inbox(FakeGmail([])) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_intake.py -v`
Expected: FAIL with `ImportError` (no `src.intake.gmail_client`)

- [ ] **Step 3: Implement client types and service**

`src/intake/gmail_client.py` (types + real client; real client exercised in Task 8):

```python
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from googleapiclient.discovery import build


@dataclass
class Attachment:
    filename: str
    content: bytes


@dataclass
class EmailMessage:
    message_id: str
    subject: str
    body: str
    received_at: datetime
    attachments: list[Attachment] = field(default_factory=list)


class GmailClientProtocol(Protocol):
    def fetch_unread_with_attachments(self) -> list[EmailMessage]: ...
    def mark_processed(self, message_id: str) -> None: ...


class GmailClient:
    def __init__(self, credentials):
        self._svc = build("gmail", "v1", credentials=credentials)

    def fetch_unread_with_attachments(self) -> list[EmailMessage]:
        listing = self._svc.users().messages().list(
            userId="me", q="is:unread has:attachment", maxResults=10
        ).execute()
        return [self._fetch(m["id"]) for m in listing.get("messages", [])]

    def mark_processed(self, message_id: str) -> None:
        self._svc.users().messages().modify(
            userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
        ).execute()

    def _fetch(self, message_id: str) -> EmailMessage:
        msg = self._svc.users().messages().get(userId="me", id=message_id).execute()
        headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
        received = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)
        attachments = []
        for part in msg["payload"].get("parts", []):
            filename = part.get("filename")
            att_id = part.get("body", {}).get("attachmentId")
            if filename and att_id:
                data = self._svc.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=att_id
                ).execute()["data"]
                attachments.append(Attachment(filename, base64.urlsafe_b64decode(data)))
        return EmailMessage(
            message_id=message_id,
            subject=headers.get("subject", ""),
            body=msg.get("snippet", ""),
            received_at=received,
            attachments=attachments,
        )
```

`src/intake/service.py`:

```python
from src.classifier.service import classify_and_log
from src.documents.models import Document
from src.documents.service import is_supported, save_document
from src.intake.gmail_client import GmailClientProtocol


def process_inbox(client: GmailClientProtocol) -> list[Document]:
    saved: list[Document] = []
    for message in client.fetch_unread_with_attachments():
        for attachment in message.attachments:
            if not is_supported(attachment.filename):
                continue
            doc = save_document(
                attachment.content, attachment.filename,
                source="email", detected_at=message.received_at,
            )
            classify_and_log(
                doc.id, doc.filename, subject=message.subject, body=message.body
            )
            saved.append(doc)
        client.mark_processed(message.message_id)
    return saved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_intake.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/intake tests/test_intake.py
git commit -m "feat: gmail intake pipeline saving and classifying attachments (rows 1-2)"
```

---

### Task 8: Gmail poller wiring (near-real-time monitoring)

**Files:**
- Modify: `src/main.py` (lifespan)
- Create: `tests/test_poller.py`

**Interfaces:**
- Consumes: `process_inbox` (Task 7), `GmailClient` (Task 7), `get_credentials` (Task 2), `settings.enable_gmail_poller`, `settings.gmail_poll_seconds` (Task 1).
- Produces: background asyncio task that calls `process_inbox` every `gmail_poll_seconds` while the app runs, only when `ENABLE_GMAIL_POLLER=true`. Exposes `src.main.poll_inbox_forever(client, interval)` for tests.

- [ ] **Step 1: Write the failing test**

`tests/test_poller.py`:

```python
import asyncio

import pytest

from src import main


@pytest.mark.anyio
async def test_poll_inbox_forever_calls_process_each_interval(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "process_inbox", lambda client: calls.append(client))
    task = asyncio.create_task(main.poll_inbox_forever(client="fake", interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    assert len(calls) >= 2
    assert calls[0] == "fake"
```

Add `anyio` marker support: append to `pyproject.toml` `[tool.pytest.ini_options]`: `anyio_mode = "auto"` — or simpler, add fixture in `tests/test_poller.py`:

```python
@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_poller.py -v`
Expected: FAIL with `AttributeError: module 'src.main' has no attribute 'poll_inbox_forever'`

- [ ] **Step 3: Implement in src/main.py**

Add to `src/main.py`:

```python
import asyncio
import logging

from src.config import settings
from src.intake.service import process_inbox

logger = logging.getLogger(__name__)


async def poll_inbox_forever(client, interval: float) -> None:
    while True:
        try:
            await asyncio.to_thread(process_inbox, client)
        except Exception:
            logger.exception("gmail poll failed; retrying next interval")
        await asyncio.sleep(interval)
```

Replace the lifespan with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    poller = None
    if settings.enable_gmail_poller:
        from scripts.google_auth import get_credentials
        from src.intake.gmail_client import GmailClient

        client = GmailClient(get_credentials())
        poller = asyncio.create_task(
            poll_inbox_forever(client, settings.gmail_poll_seconds)
        )
    yield
    if poller:
        poller.cancel()
```

Note: `await asyncio.to_thread(...)` wrapper means the fake in the test is called synchronously inside a thread — that's fine.

- [ ] **Step 4: Run all tests**

Run: `.venv\Scripts\pytest -v`
Expected: PASS (all)

- [ ] **Step 5: Live end-to-end check (rows 1–2 acceptance)**

1. Set `ENABLE_GMAIL_POLLER=true` and a real `ANTHROPIC_API_KEY` in `.env`.
2. Run `.venv\Scripts\uvicorn src.main:app --port 8000`.
3. Send the demo inbox an email with a `.docx` attachment named like a contract revision, and one plain email with no attachment.
4. Within ~30s, `GET http://localhost:8000/documents` shows the docx with `is_contract_revision`, confidence, and reasoning; the plain email caused no error in logs.

Expected: both behaviors observed. Record actual output in the PR/commit message.

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_poller.py pyproject.toml
git commit -m "feat: background gmail poller for near-real-time inbox monitoring (row 1)"
```

---

### Task 9: Locator module — Drive search (row 4)

**Files:**
- Create: `src/locator/__init__.py`, `src/locator/schemas.py`, `src/locator/drive_client.py`, `src/locator/service.py`, `src/locator/router.py`, `tests/test_locator.py`
- Modify: `src/main.py` (include router)

**Interfaces:**
- Consumes: `get_credentials` (Task 2).
- Produces:
  - `DriveFile(BaseModel)`: `file_id: str`, `name: str`, `modified_time: datetime`, `mime_type: str`, `web_view_link: str | None`.
  - `service.search_contracts(query: str, drive) -> list[DriveFile]` — searches PDF/DOCX files whose name contains the query, ordered by Drive relevance/recency.
  - `GET /drive/search?q=<query>` → `{"results": [DriveFile...]}` (empty list, not error, on no matches).

- [ ] **Step 1: Write the failing tests**

`tests/test_locator.py`:

```python
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.locator import router as locator_router
from src.locator import service
from src.locator.schemas import DriveFile
from src.main import app


class FakeDrive:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def search(self, q: str):
        self.queries.append(q)
        return self.rows


def _file(name):
    return DriveFile(
        file_id="f1", name=name, mime_type="application/pdf",
        modified_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
        web_view_link="https://drive.google.com/x",
    )


def test_search_contracts_passes_query_and_returns_rows():
    fake = FakeDrive([_file("Acme MSA v3.pdf")])
    results = service.search_contracts("acme", drive=fake)
    assert [r.name for r in results] == ["Acme MSA v3.pdf"]
    assert "acme" in fake.queries[0]


def test_search_endpoint_empty_result_is_200(monkeypatch):
    monkeypatch.setattr(locator_router, "get_drive_client", lambda: FakeDrive([]))
    client = TestClient(app)
    resp = client.get("/drive/search", params={"q": "nonexistent"})
    assert resp.status_code == 200
    assert resp.json() == {"results": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_locator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.locator'`

- [ ] **Step 3: Implement the module**

`src/locator/schemas.py`:

```python
from datetime import datetime

from pydantic import BaseModel


class DriveFile(BaseModel):
    file_id: str
    name: str
    modified_time: datetime
    mime_type: str
    web_view_link: str | None = None
```

`src/locator/drive_client.py`:

```python
from datetime import datetime

from googleapiclient.discovery import build

from src.locator.schemas import DriveFile

CONTRACT_MIMES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.document",
)


class DriveClient:
    def __init__(self, credentials):
        self._svc = build("drive", "v3", credentials=credentials)

    def search(self, q: str) -> list[DriveFile]:
        mime_clause = " or ".join(f"mimeType='{m}'" for m in CONTRACT_MIMES)
        escaped = q.replace("'", r"\'")
        listing = self._svc.files().list(
            q=f"name contains '{escaped}' and ({mime_clause}) and trashed=false",
            fields="files(id,name,modifiedTime,mimeType,webViewLink)",
            pageSize=10,
        ).execute()
        return [
            DriveFile(
                file_id=f["id"], name=f["name"], mime_type=f["mimeType"],
                modified_time=datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00")),
                web_view_link=f.get("webViewLink"),
            )
            for f in listing.get("files", [])
        ]
```

`src/locator/service.py`:

```python
from src.locator.schemas import DriveFile


def search_contracts(query: str, drive) -> list[DriveFile]:
    return drive.search(query)
```

`src/locator/router.py`:

```python
from fastapi import APIRouter

from src.locator.schemas import DriveFile
from src.locator.service import search_contracts


def get_drive_client():
    from scripts.google_auth import get_credentials
    from src.locator.drive_client import DriveClient

    return DriveClient(get_credentials())


router = APIRouter()


@router.get("/drive/search")
def drive_search(q: str) -> dict[str, list[DriveFile]]:
    return {"results": search_contracts(q, drive=get_drive_client())}
```

In `src/main.py` add:

```python
from src.locator import router as locator_router
app.include_router(locator_router.router)
```

- [ ] **Step 4: Run all tests**

Run: `.venv\Scripts\pytest -v`
Expected: PASS (all)

- [ ] **Step 5: Live check (row 4 acceptance)**

With the server running and a couple of PDFs placed in the demo account's Drive:
`GET http://localhost:8000/drive/search?q=<keyword>` returns them with name/modifiedTime; a nonsense query returns `{"results": []}`.

- [ ] **Step 6: Commit**

```bash
git add src/locator src/main.py tests/test_locator.py
git commit -m "feat: drive search for contracts (row 4)"
```

---

### Task 10: Web repo scaffold

**Files (all in `D:\SmartWave\contract-review-web`):**
- Create: entire Next.js app scaffold, bulletproof-react folders, Vitest config, `.env.local`

**Interfaces:**
- Produces: running Next.js dev server on port 3000; folder skeleton `src/app`, `src/components/ui`, `src/features/{upload,review-queue,drive-search}`, `src/lib`, `src/types`; `npm test` runs Vitest. Consumed by Tasks 11–15.

- [ ] **Step 1: Scaffold the app**

Run from `D:\SmartWave`:

```powershell
npx create-next-app@latest contract-review-web --typescript --tailwind --eslint --app --src-dir --use-npm --import-alias "@/*"
```

Expected: project created; `cd contract-review-web; npm run dev` serves the starter page on http://localhost:3000. Stop it.

- [ ] **Step 2: Add Vitest + Testing Library**

```powershell
npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

Create `vitest.config.ts`:

```ts
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    globals: true,
  },
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
});
```

Create `vitest.setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

Add to `package.json` scripts: `"test": "vitest run"`.

- [ ] **Step 3: Create folder skeleton and env**

```powershell
mkdir src\components\ui, src\features\upload, src\features\review-queue, src\features\drive-search, src\lib, src\types
```

`.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Also create `.env.example` with the same content (`.env.local` is gitignored by create-next-app).

- [ ] **Step 4: Verify test runner works**

Create `src/lib/smoke.test.ts`:

```ts
import { expect, test } from 'vitest';

test('vitest runs', () => {
  expect(1 + 1).toBe(2);
});
```

Run: `npm test`
Expected: 1 passed.

- [ ] **Step 5: Commit (new repo)**

```bash
git init
git add -A
git commit -m "feat: next.js scaffold with bulletproof-react layout and vitest"
```

---

### Task 11: Design system — generic tokens + base UI components

**Files (in `contract-review-web`):**
- Modify: `src/app/globals.css`, `src/app/layout.tsx`
- Create: `src/components/ui/button.tsx`, `src/components/ui/card.tsx`, `src/components/ui/badge.tsx`, `src/components/ui/empty-state.tsx`, `src/components/ui/ui.test.tsx`

**Interfaces:**
- Produces (consumed by Tasks 13–15):
  - CSS custom properties: `--color-primary`, `--color-primary-hover`, `--color-primary-foreground`, `--color-surface`, `--color-surface-raised`, `--color-border`, `--color-text`, `--color-text-muted`, `--color-success`, `--color-danger`, `--color-warning`, plus Tailwind v4 `@theme inline` mappings `primary`, `surface`, `surface-raised`, `border`, `text`, `text-muted`, `success`, `danger`, `warning`.
  - `<Button variant="primary" | "secondary" | "ghost">` (extends native button props).
  - `<Card>` container; `<Badge tone="success" | "danger" | "warning" | "neutral">`.
  - `<EmptyState title={string} description={string}>`.

> **Brand note:** Generic, professional palette — deliberately not tailored to any client brand (per Ryan 2026-08-26). All values live in one tokens file, so client branding can be applied later as a one-file change in `globals.css`. Font: Inter.

- [ ] **Step 1: Write the failing component tests**

`src/components/ui/ui.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { Badge } from './badge';
import { Button } from './button';
import { EmptyState } from './empty-state';

test('button renders its label', () => {
  render(<Button variant="primary">Upload</Button>);
  expect(screen.getByRole('button', { name: 'Upload' })).toBeInTheDocument();
});

test('badge tones map to token classes', () => {
  render(<Badge tone="success">Contract revision</Badge>);
  expect(screen.getByText('Contract revision').className).toContain('success');
});

test('empty state shows title and description', () => {
  render(<EmptyState title="No matching contracts found" description="Try a different keyword." />);
  expect(screen.getByText('No matching contracts found')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — cannot resolve `./badge`, `./button`, `./empty-state`.

- [ ] **Step 3: Write the tokens**

Replace `src/app/globals.css` with:

```css
@import 'tailwindcss';

:root {
  /* Generic professional palette — ONE place to change
     if client branding is applied later. */
  --color-primary: #1b3fa0;
  --color-primary-hover: #16337f;
  --color-primary-foreground: #ffffff;
  --color-surface: #f7f8fb;
  --color-surface-raised: #ffffff;
  --color-border: #dde2ee;
  --color-text: #101828;
  --color-text-muted: #5b6474;
  --color-success: #0e7a4d;
  --color-danger: #b42318;
  --color-warning: #b54708;
}

@theme inline {
  --color-primary: var(--color-primary);
  --color-primary-hover: var(--color-primary-hover);
  --color-primary-foreground: var(--color-primary-foreground);
  --color-surface: var(--color-surface);
  --color-surface-raised: var(--color-surface-raised);
  --color-border: var(--color-border);
  --color-text: var(--color-text);
  --color-text-muted: var(--color-text-muted);
  --color-success: var(--color-success);
  --color-danger: var(--color-danger);
  --color-warning: var(--color-warning);
  --font-sans: 'Inter', ui-sans-serif, system-ui, sans-serif;
}

body {
  background: var(--color-surface);
  color: var(--color-text);
  font-family: var(--font-sans);
}
```

In `src/app/layout.tsx`, load Inter via `next/font/google` (replace the default Geist setup):

```tsx
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata = { title: 'Contract Review Agent' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
```

- [ ] **Step 4: Write the base components**

`src/components/ui/button.tsx`:

```tsx
import { type ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'ghost';

const styles: Record<Variant, string> = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary-hover',
  secondary: 'bg-surface-raised border border-border text-text hover:bg-surface',
  ghost: 'text-primary hover:bg-surface',
};

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 ${styles[variant]} ${className}`}
      {...props}
    />
  );
}
```

`src/components/ui/card.tsx`:

```tsx
import { type HTMLAttributes } from 'react';

export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-lg border border-border bg-surface-raised p-4 shadow-sm ${className}`}
      {...props}
    />
  );
}
```

`src/components/ui/badge.tsx`:

```tsx
import { type HTMLAttributes } from 'react';

type Tone = 'success' | 'danger' | 'warning' | 'neutral';

const tones: Record<Tone, string> = {
  success: 'bg-success/10 text-success',
  danger: 'bg-danger/10 text-danger',
  warning: 'bg-warning/10 text-warning',
  neutral: 'bg-border/40 text-text-muted',
};

export function Badge({
  tone = 'neutral',
  className = '',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]} ${className}`}
      {...props}
    />
  );
}
```

`src/components/ui/empty-state.tsx`:

```tsx
export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-lg border border-dashed border-border py-12 text-center">
      <p className="font-medium">{title}</p>
      <p className="text-sm text-text-muted">{description}</p>
    </div>
  );
}
```

- [ ] **Step 5: Run tests and dev server**

Run: `npm test` — Expected: PASS (plus smoke test).
Run: `npm run dev`, view http://localhost:3000 — Expected: page renders with Inter on the light surface background. Stop it.

- [ ] **Step 6: Commit**

```bash
git add src/app src/components
git commit -m "feat: design tokens and base ui components"
```

---

### Task 12: Web API client + shared types

**Files (in `contract-review-web`):**
- Create: `src/lib/api.ts`, `src/types/api.ts`, `src/lib/api.test.ts`
- Delete: `src/lib/smoke.test.ts`

**Interfaces:**
- Consumes: backend endpoints (Tasks 6, 9).
- Produces (consumed by Tasks 13–15):
  - `DocumentOut` type: `{ id: number; filename: string; source: 'email' | 'upload'; mime_type: string; detected_at: string; is_contract_revision: boolean | null; confidence: number | null; reasoning: string | null }`.
  - `DriveFile` type: `{ file_id: string; name: string; modified_time: string; mime_type: string; web_view_link: string | null }`.
  - `api.uploadContract(file: File): Promise<DocumentOut>` — throws `Error` with backend `detail` on non-2xx.
  - `api.listDocuments(): Promise<DocumentOut[]>`
  - `api.searchDrive(q: string): Promise<DriveFile[]>`

- [ ] **Step 1: Write the failing tests**

`src/lib/api.test.ts`:

```ts
import { afterEach, expect, test, vi } from 'vitest';
import { listDocuments, searchDrive, uploadContract } from './api';

afterEach(() => vi.restoreAllMocks());

function mockFetch(status: number, body: unknown) {
  return vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: status < 300,
    status,
    json: async () => body,
  }));
}

test('listDocuments returns documents', async () => {
  mockFetch(200, [{ id: 1, filename: 'nda.pdf' }]);
  const docs = await listDocuments();
  expect(docs[0].filename).toBe('nda.pdf');
});

test('uploadContract posts multipart and surfaces backend error detail', async () => {
  mockFetch(422, { detail: 'Unsupported file type. Upload a PDF or DOCX.' });
  await expect(uploadContract(new File(['x'], 'cat.gif'))).rejects.toThrow(/PDF or DOCX/);
});

test('searchDrive unwraps results', async () => {
  mockFetch(200, { results: [{ file_id: 'f1', name: 'Acme MSA.pdf' }] });
  const results = await searchDrive('acme');
  expect(results[0].name).toBe('Acme MSA.pdf');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — cannot resolve `./api`.

- [ ] **Step 3: Implement types and client**

`src/types/api.ts`:

```ts
export type DocumentOut = {
  id: number;
  filename: string;
  source: 'email' | 'upload';
  mime_type: string;
  detected_at: string;
  is_contract_revision: boolean | null;
  confidence: number | null;
  reasoning: string | null;
};

export type DriveFile = {
  file_id: string;
  name: string;
  modified_time: string;
  mime_type: string;
  web_view_link: string | null;
};
```

`src/lib/api.ts`:

```ts
import type { DocumentOut, DriveFile } from '@/types/api';

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail ?? `Request failed (${res.status})`);
  return body as T;
}

export function listDocuments(): Promise<DocumentOut[]> {
  return request('/documents');
}

export function uploadContract(file: File): Promise<DocumentOut> {
  const form = new FormData();
  form.append('file', file);
  return request('/upload', { method: 'POST', body: form });
}

export async function searchDrive(q: string): Promise<DriveFile[]> {
  const body = await request<{ results: DriveFile[] }>(
    `/drive/search?q=${encodeURIComponent(q)}`,
  );
  return body.results;
}
```

Delete `src/lib/smoke.test.ts`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib src/types
git rm src/lib/smoke.test.ts
git commit -m "feat: typed api client for backend endpoints"
```

---

### Task 13: Upload feature (row 3 UI)

**Files (in `contract-review-web`):**
- Create: `src/features/upload/upload-form.tsx`, `src/features/upload/upload-form.test.tsx`, `src/app/upload/page.tsx`

**Interfaces:**
- Consumes: `uploadContract` (Task 12), `Button`, `Card`, `Badge` (Task 11).
- Produces: `<UploadForm />` client component; page at `/upload`.

- [ ] **Step 1: Write the failing tests**

`src/features/upload/upload-form.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';

const uploadContract = vi.fn();
vi.mock('@/lib/api', () => ({ uploadContract: (...a: unknown[]) => uploadContract(...a) }));

import { UploadForm } from './upload-form';

test('shows confirmation with classification after upload', async () => {
  uploadContract.mockResolvedValue({
    id: 1, filename: 'nda.pdf', is_contract_revision: true, confidence: 0.9,
    reasoning: 'stub', source: 'upload', mime_type: 'application/pdf',
    detected_at: '2026-08-26T00:00:00Z',
  });
  render(<UploadForm />);
  const input = screen.getByLabelText(/choose a contract/i);
  await userEvent.upload(input, new File(['%PDF'], 'nda.pdf', { type: 'application/pdf' }));
  await userEvent.click(screen.getByRole('button', { name: /upload/i }));
  await waitFor(() => expect(screen.getByText(/received nda\.pdf/i)).toBeInTheDocument());
  expect(screen.getByText(/contract revision/i)).toBeInTheDocument();
});

test('shows backend error for unsupported type', async () => {
  uploadContract.mockRejectedValue(new Error('Unsupported file type. Upload a PDF or DOCX.'));
  render(<UploadForm />);
  const input = screen.getByLabelText(/choose a contract/i);
  await userEvent.upload(input, new File(['x'], 'cat.gif', { type: 'image/gif' }));
  await userEvent.click(screen.getByRole('button', { name: /upload/i }));
  await waitFor(() => expect(screen.getByText(/PDF or DOCX/)).toBeInTheDocument());
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — cannot resolve `./upload-form`.

- [ ] **Step 3: Implement the form and page**

`src/features/upload/upload-form.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { uploadContract } from '@/lib/api';
import type { DocumentOut } from '@/types/api';

export function UploadForm() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<DocumentOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await uploadContract(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-lg">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="text-sm font-medium" htmlFor="contract-file">
          Choose a contract (PDF or DOCX)
        </label>
        <input
          id="contract-file"
          type="file"
          accept=".pdf,.docx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="text-sm"
        />
        <Button type="submit" disabled={!file || busy}>
          {busy ? 'Uploading…' : 'Upload'}
        </Button>
      </form>
      {result && (
        <div className="mt-4 flex items-center gap-2">
          <p className="text-sm">Received {result.filename}.</p>
          <Badge tone={result.is_contract_revision ? 'success' : 'neutral'}>
            {result.is_contract_revision ? 'Contract revision' : 'Not a contract revision'}
          </Badge>
        </div>
      )}
      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
    </Card>
  );
}
```

`src/app/upload/page.tsx`:

```tsx
import { UploadForm } from '@/features/upload/upload-form';

export default function UploadPage() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="mb-6 text-2xl font-semibold">Upload a contract</h1>
      <UploadForm />
    </main>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: PASS.

- [ ] **Step 5: Live check against the backend**

With backend on :8000 and `npm run dev`: upload a real PDF at http://localhost:3000/upload → confirmation + classification badge appear (row 3 acceptance).

- [ ] **Step 6: Commit**

```bash
git add src/features/upload src/app/upload
git commit -m "feat: manual contract upload screen (row 3)"
```

---

### Task 14: Review queue feature (rows 1–2 visible in UI)

**Files (in `contract-review-web`):**
- Create: `src/features/review-queue/document-list.tsx`, `src/features/review-queue/document-list.test.tsx`
- Modify: `src/app/page.tsx` (home page becomes the review queue)

**Interfaces:**
- Consumes: `listDocuments` (Task 12), `Card`, `Badge`, `EmptyState` (Task 11).
- Produces: `<DocumentList documents={DocumentOut[]} />` (presentational) rendered by the home page, which fetches server-side with `listDocuments()` and `export const dynamic = 'force-dynamic'`.

- [ ] **Step 1: Write the failing tests**

`src/features/review-queue/document-list.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import type { DocumentOut } from '@/types/api';
import { DocumentList } from './document-list';

const doc = (over: Partial<DocumentOut>): DocumentOut => ({
  id: 1, filename: 'msa-v2.docx', source: 'email',
  mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  detected_at: '2026-08-26T05:00:00Z', is_contract_revision: true,
  confidence: 0.93, reasoning: 'Redlined MSA', ...over,
});

test('renders documents with classification badge and confidence', () => {
  render(<DocumentList documents={[doc({})]} />);
  expect(screen.getByText('msa-v2.docx')).toBeInTheDocument();
  expect(screen.getByText(/contract revision/i)).toBeInTheDocument();
  expect(screen.getByText(/93%/)).toBeInTheDocument();
});

test('empty list shows empty state', () => {
  render(<DocumentList documents={[]} />);
  expect(screen.getByText(/no contracts detected yet/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — cannot resolve `./document-list`.

- [ ] **Step 3: Implement list + home page**

`src/features/review-queue/document-list.tsx`:

```tsx
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import type { DocumentOut } from '@/types/api';

export function DocumentList({ documents }: { documents: DocumentOut[] }) {
  if (documents.length === 0) {
    return (
      <EmptyState
        title="No contracts detected yet"
        description="Contracts arriving in the monitored inbox or uploaded manually will appear here."
      />
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {documents.map((doc) => (
        <li key={doc.id}>
          <Card className="flex items-center justify-between gap-4">
            <div>
              <p className="font-medium">{doc.filename}</p>
              <p className="text-sm text-text-muted">
                via {doc.source} · {new Date(doc.detected_at).toLocaleString()}
              </p>
              {doc.reasoning && <p className="mt-1 text-sm text-text-muted">{doc.reasoning}</p>}
            </div>
            <div className="flex items-center gap-2">
              {doc.is_contract_revision === null ? (
                <Badge tone="warning">Classifying…</Badge>
              ) : doc.is_contract_revision ? (
                <Badge tone="success">Contract revision</Badge>
              ) : (
                <Badge tone="neutral">Not a contract revision</Badge>
              )}
              {doc.confidence !== null && (
                <span className="text-sm text-text-muted">
                  {Math.round(doc.confidence * 100)}%
                </span>
              )}
            </div>
          </Card>
        </li>
      ))}
    </ul>
  );
}
```

`src/app/page.tsx`:

```tsx
import Link from 'next/link';
import { DocumentList } from '@/features/review-queue/document-list';
import { listDocuments } from '@/lib/api';

export const dynamic = 'force-dynamic';

export default async function HomePage() {
  const documents = await listDocuments();
  return (
    <main className="mx-auto max-w-3xl p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Review queue</h1>
        <nav className="flex gap-4 text-sm">
          <Link className="text-primary hover:underline" href="/upload">Upload</Link>
          <Link className="text-primary hover:underline" href="/search">Drive search</Link>
        </nav>
      </div>
      <DocumentList documents={documents} />
    </main>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: PASS.

- [ ] **Step 5: Live check**

Backend running with a couple of documents in the DB → http://localhost:3000 lists them with badges; empty DB shows the empty state.

- [ ] **Step 6: Commit**

```bash
git add src/features/review-queue src/app/page.tsx
git commit -m "feat: review queue listing detected and uploaded contracts"
```

---

### Task 15: Drive search feature (rows 4 + 6 UI)

**Files (in `contract-review-web`):**
- Create: `src/features/drive-search/search-panel.tsx`, `src/features/drive-search/search-panel.test.tsx`, `src/app/search/page.tsx`

**Interfaces:**
- Consumes: `searchDrive` (Task 12), `Button`, `Card`, `EmptyState` (Task 11).
- Produces: `<SearchPanel />` client component; page at `/search`. Results show file name, modified date, and a Drive link (row 6 acceptance: key identifying details, scannable list, graceful no-results state).

- [ ] **Step 1: Write the failing tests**

`src/features/drive-search/search-panel.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';

const searchDrive = vi.fn();
vi.mock('@/lib/api', () => ({ searchDrive: (...a: unknown[]) => searchDrive(...a) }));

import { SearchPanel } from './search-panel';

test('renders results with name and modified date', async () => {
  searchDrive.mockResolvedValue([{
    file_id: 'f1', name: 'Acme MSA v3.pdf', mime_type: 'application/pdf',
    modified_time: '2026-08-01T00:00:00Z', web_view_link: 'https://drive.google.com/x',
  }]);
  render(<SearchPanel />);
  await userEvent.type(screen.getByRole('searchbox'), 'acme');
  await userEvent.click(screen.getByRole('button', { name: /search/i }));
  await waitFor(() => expect(screen.getByText('Acme MSA v3.pdf')).toBeInTheDocument());
  expect(screen.getByRole('link', { name: /open in drive/i })).toHaveAttribute(
    'href', 'https://drive.google.com/x',
  );
});

test('no matches shows graceful empty state', async () => {
  searchDrive.mockResolvedValue([]);
  render(<SearchPanel />);
  await userEvent.type(screen.getByRole('searchbox'), 'zzz');
  await userEvent.click(screen.getByRole('button', { name: /search/i }));
  await waitFor(() =>
    expect(screen.getByText(/no matching contracts found/i)).toBeInTheDocument(),
  );
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — cannot resolve `./search-panel`.

- [ ] **Step 3: Implement the panel and page**

`src/features/drive-search/search-panel.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { searchDrive } from '@/lib/api';
import type { DriveFile } from '@/types/api';

export function SearchPanel() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<DriveFile[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    try {
      setResults(await searchDrive(query.trim()));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search contracts in Drive…"
          className="w-full rounded-md border border-border bg-surface-raised px-3 py-2 text-sm"
        />
        <Button type="submit" disabled={busy}>
          {busy ? 'Searching…' : 'Search'}
        </Button>
      </form>
      {results !== null && results.length === 0 && (
        <EmptyState
          title="No matching contracts found"
          description="Try a different keyword, or upload the contract manually."
        />
      )}
      {results !== null && results.length > 0 && (
        <ul className="flex flex-col gap-3">
          {results.map((file) => (
            <li key={file.file_id}>
              <Card className="flex items-center justify-between gap-4">
                <div>
                  <p className="font-medium">{file.name}</p>
                  <p className="text-sm text-text-muted">
                    Modified {new Date(file.modified_time).toLocaleDateString()}
                  </p>
                </div>
                {file.web_view_link && (
                  <a
                    className="text-sm text-primary hover:underline"
                    href={file.web_view_link}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open in Drive
                  </a>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

`src/app/search/page.tsx`:

```tsx
import { SearchPanel } from '@/features/drive-search/search-panel';

export default function SearchPage() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="mb-6 text-2xl font-semibold">Find a contract in Drive</h1>
      <SearchPanel />
    </main>
  );
}
```

- [ ] **Step 4: Run tests, lint, build**

Run: `npm test` — Expected: PASS.
Run: `npm run build` — Expected: build succeeds with no type errors.

- [ ] **Step 5: Live end-to-end check (Friday demo dry run)**

Backend + web running:
1. Email a `.docx` to the demo inbox → appears in review queue within ~30s with classification badge.
2. Upload a PDF at `/upload` → confirmation + badge.
3. Search a Drive keyword at `/search` → results with name/date; nonsense query → "No matching contracts found".

Expected: all three flows pass — that is rows 1, 2, 3, 4, 6 demonstrated.

- [ ] **Step 6: Commit**

```bash
git add src/features/drive-search src/app/search
git commit -m "feat: drive search screen with results and empty state (rows 4, 6)"
```

---

## Out of scope for this plan (Phase 2 plan, next week)

Rows 5, 7–14: clarifying questions, contract confirmation step, automatic review + suggested redlines, latency metric, Apply/Reject UI, versioning + anchor rebasing, output format (pending 917 confirmation), A2A endpoint + agent card, RAG grounding.

## Open questions carried

1. Output format confirmation with 917 (needed before Phase 2 `redliner`).
2. RAG corpus source (needed before Phase 3).
