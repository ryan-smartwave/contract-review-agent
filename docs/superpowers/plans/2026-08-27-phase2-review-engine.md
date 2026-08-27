# Contract Review Agent — Phase 2 Review Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship tracker rows 5, 7–14 — automatic review with clause-anchored suggested redlines, one-click Apply/Reject with immutable versioning, Drive confirmation flow, clarifying questions — plus the A2A endpoint and the four limitations.md fixes.

**Architecture:** Same multi-repo layout as Phase 1. Backend adds a `reviewer` capability (LLM generates `SuggestionDraft`s validated against the document text — an anchor is the exact `original_text` excerpt, kept only if it occurs exactly once), a `redliner` capability (Apply = string-replace the anchor in the latest `DocumentVersion`'s text, producing a new version; original file never touched — the confirmed output format is **new version per apply**), Drive download/confirm in `locator`, and an A2A server mounted on the FastAPI app via `a2a-sdk`. Frontend adds a document-viewer feature (suggestion cards with Apply/Reject, version history, anchored-span highlighting) and upgrades search/upload flows.

**Tech Stack:** Existing Phase 1 stack + `a2a-sdk` (backend). No new frontend dependencies.

**Spec:** `docs/superpowers/specs/2026-08-26-contract-review-agent-design.md`
**Also read:** `docs/limitations.md` (the four unchecked items this plan fixes).

## Global Constraints

- **No vendor AI SDK imports** — model access only via `src/llm/factory.get_chat_model()` (LangChain `init_chat_model`, provider from `MODEL_NAME`).
- **Documents are immutable** — Apply never edits a file or a prior version; it creates the next `DocumentVersion`. Reject changes only the suggestion's status.
- **Suggestions are independent** (tracker rows 11–13): actioning one never changes another's status; an anchor invalidated by a prior apply becomes `stale`, never silently dropped; rejected suggestions stay visible.
- **Anchors are content-based**: a suggestion's `original_text` must occur **exactly once** in the document text at creation time; drafts violating this are discarded during review.
- Supported document types stay `.pdf`/`.docx` (Google Docs are exported to PDF on Drive confirm).
- **Coding principles (CLAUDE.md):** DRY, KISS, self-documenting code, YAGNI. Web import rule: shared → features → app; features never import each other. All UI colors via tokens.
- Backend commands from `D:\SmartWave\contract-review-agent` (venv at `.venv\Scripts\`); web commands from `D:\SmartWave\contract-review-web`. Windows.
- Suggestion statuses are exactly: `pending`, `applied`, `rejected`, `stale`.

---

### Task 1: Content-aware classification

**Files:**
- Modify: `src/classifier/service.py` (prompts + signature)
- Modify: `src/intake/service.py`, `src/intake/router.py` (pass extracted text)
- Test: `tests/test_classifier.py`, `tests/test_intake.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `src.documents.extract.extract_text_preview(content: bytes, filename: str, max_chars: int = 4000) -> str` (already committed).
- Produces: `classify_and_log(document_id, filename, subject="", body="", source="email", document_text="", llm=None) -> ClassificationResult`. Body is capped at 2000 chars, document_text at 4000, inside the function. Task 6 reuses the extraction constant `FULL_TEXT_MAX_CHARS = 50_000` introduced here in `src/documents/extract.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classifier.py`:

```python
def test_prompt_includes_document_text_and_caps_body():
    doc = save_document(b"x", "renamed.pdf", source="email")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=False, confidence=0.9, reasoning="Newsletter content.",
    ))
    long_body = "b" * 3000
    service.classify_and_log(
        doc.id, doc.filename, subject="s", body=long_body,
        document_text="August Newsletter: our latest promos", llm=fake,
    )
    prompt = fake.prompts[0]
    assert "August Newsletter: our latest promos" in prompt
    assert "b" * 2000 in prompt
    assert "b" * 2001 not in prompt


def test_upload_prompt_includes_document_text():
    doc = save_document(b"x", "Apex_Draft.pdf", source="upload")
    fake = FakeStructuredLLM(ClassificationResult(
        is_contract_revision=True, confidence=0.9, reasoning="ok",
    ))
    service.classify_and_log(
        doc.id, doc.filename, source="upload",
        document_text="MASTER SERVICES AGREEMENT between Apex and Globe", llm=fake,
    )
    assert "MASTER SERVICES AGREEMENT" in fake.prompts[0]
```

Append to `tests/test_intake.py` (inside `test_process_inbox_saves_supported_attachments`, extend the monkeypatched stub and add an assertion — replace the existing monkeypatch lambda with a capturing fake):

```python
def test_process_inbox_passes_extracted_text(monkeypatch):
    captured = {}

    def fake_classify(document_id, filename, **kw):
        captured.update(kw)
        return ClassificationResult(is_contract_revision=False, confidence=0.9, reasoning="x")

    monkeypatch.setattr(service, "classify_and_log", fake_classify)
    monkeypatch.setattr(service, "extract_text_preview", lambda content, fn, max_chars=50000: "EXTRACTED BODY TEXT")
    fake = FakeGmail([_msg("m1", "s", [Attachment("a.pdf", b"pdf")])])
    service.process_inbox(fake)
    assert captured["document_text"] == "EXTRACTED BODY TEXT"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_classifier.py tests/test_intake.py -v`
Expected: FAIL — `classify_and_log` has no `document_text` param; `src.intake.service` has no `extract_text_preview`.

- [ ] **Step 3: Implement**

In `src/documents/extract.py` add a module constant:

```python
FULL_TEXT_MAX_CHARS = 50_000
```

In `src/classifier/service.py`, replace the two prompts and the function:

```python
BODY_MAX_CHARS = 2000
DOC_TEXT_MAX_CHARS = 4000

EMAIL_PROMPT = """You are a legal-operations email triage assistant.
Decide whether this email + attachment is a CONTRACT REVISION \
(a new draft, redline, or amendment of a contract) or not \
(invoice, newsletter, receipt, general correspondence, etc.).
Judge primarily from the document text when present; filenames can be misleading.

Attachment filename: {filename}
Email subject: {subject}
Email body (may be truncated or empty): {body}
Document text (first pages; may be empty): {document_text}
"""

UPLOAD_PROMPT = """You are a legal-operations document triage assistant.
A user manually uploaded this document for contract review.
Decide whether it is a CONTRACT REVISION \
(a new draft, redline, or amendment of a contract) or not \
(invoice, newsletter, receipt, other paperwork, etc.).
Judge primarily from the document text when present; filenames can be misleading.

Uploaded filename: {filename}
Document text (first pages; may be empty): {document_text}
"""


def classify_and_log(
    document_id: int,
    filename: str,
    subject: str = "",
    body: str = "",
    source: str = "email",
    document_text: str = "",
    llm=None,
) -> ClassificationResult:
    llm = llm or get_chat_model()
    structured = llm.with_structured_output(ClassificationResult)
    document_text = document_text[:DOC_TEXT_MAX_CHARS]
    if source == "upload":
        prompt = UPLOAD_PROMPT.format(filename=filename, document_text=document_text)
    else:
        prompt = EMAIL_PROMPT.format(
            filename=filename, subject=subject, body=body[:BODY_MAX_CHARS],
            document_text=document_text,
        )
    result = structured.invoke(prompt)
    with db.get_session() as session:
        session.add(ClassificationLog(document_id=document_id, **result.model_dump()))
        session.commit()
    return result
```

In `src/intake/service.py`: add `from src.documents.extract import FULL_TEXT_MAX_CHARS, extract_text_preview`, and in the attachment loop:

```python
            text = extract_text_preview(
                attachment.content, attachment.filename, max_chars=FULL_TEXT_MAX_CHARS
            )
            classify_and_log(
                doc.id, doc.filename, subject=message.subject,
                body=message.body, document_text=text,
            )
```

In `src/intake/router.py` upload endpoint, before classify:

```python
    content = await file.read()
    if not is_supported(file.filename or ""):
        raise HTTPException(422, "Unsupported file type. Upload a PDF or DOCX.")
    doc = save_document(content, file.filename, source="upload")
    text = extract_text_preview(content, file.filename, max_chars=FULL_TEXT_MAX_CHARS)
    result = classify_and_log(doc.id, doc.filename, source="upload", document_text=text)
```

(with `from src.documents.extract import FULL_TEXT_MAX_CHARS, extract_text_preview` added; keep the existing response construction).

- [ ] **Step 4: Run the full suite**

Run: `.venv\Scripts\pytest -v` — Expected: all PASS (existing prompt tests still pass because prompts only gained lines).

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "feat: content-aware classification from extracted document text"
```

---

### Task 2: Full Gmail body instead of snippet

**Files:**
- Modify: `src/intake/gmail_client.py`
- Test: `tests/test_intake.py`

**Interfaces:**
- Produces: `extract_plain_body(payload: dict) -> str` — recursively finds the first `text/plain` part's `body.data` (base64url, padding-safe) and decodes it; returns `""` if none. `_fetch` uses it, falling back to the snippet.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_intake.py`:

```python
import base64

from src.intake.gmail_client import extract_plain_body


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_extract_plain_body_nested_multipart():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "multipart/alternative", "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("Full body text here")}},
                {"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}},
            ]},
            {"mimeType": "application/pdf", "filename": "a.pdf", "body": {"attachmentId": "x"}},
        ],
    }
    assert extract_plain_body(payload) == "Full body text here"


def test_extract_plain_body_none_returns_empty():
    assert extract_plain_body({"mimeType": "multipart/mixed", "parts": []}) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_intake.py -v`
Expected: FAIL with ImportError (`extract_plain_body` undefined).

- [ ] **Step 3: Implement in `src/intake/gmail_client.py`**

```python
def extract_plain_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
                "utf-8", errors="replace"
            )
    for part in payload.get("parts", []):
        text = extract_plain_body(part)
        if text:
            return text
    return ""
```

In `_fetch`, replace `body=msg.get("snippet", "")` with:

```python
            body=extract_plain_body(msg["payload"]) or msg.get("snippet", ""),
```

- [ ] **Step 4: Run the full suite** — `.venv\Scripts\pytest -v` — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/intake/gmail_client.py tests/test_intake.py
git commit -m "fix: pass full plain-text email body to classifier, not snippet"
```

---

### Task 3: Upload classification failure → rollback + clean error

**Files:**
- Modify: `src/intake/router.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `src.documents.service.delete_document(doc: Document) -> None` (exists).
- Produces: `POST /upload` returns **502** `{"detail": "The document was received but classification failed. Please try again."}` when the LLM call raises; the document row and file are rolled back. (A handled HTTPException carries CORS headers; the previous unhandled 500 did not.)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api.py`:

```python
def test_upload_rolls_back_when_classification_fails(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(intake_router, "classify_and_log", boom)
    resp = client.post("/upload", files={"file": ("nda.pdf", b"%PDF-", "application/pdf")})
    assert resp.status_code == 502
    assert "classification failed" in resp.json()["detail"]
    assert client.get("/documents").json() == []
```

- [ ] **Step 2: Run to verify it fails** — `.venv\Scripts\pytest tests/test_api.py -v` — Expected: FAIL (raises RuntimeError → 500, and document persists).

- [ ] **Step 3: Implement** — in `src/intake/router.py`, wrap classification:

```python
    try:
        result = classify_and_log(doc.id, doc.filename, source="upload", document_text=text)
    except Exception:
        logger.exception("classification failed for upload %s", doc.filename)
        delete_document(doc)
        raise HTTPException(
            502, "The document was received but classification failed. Please try again."
        )
```

with `import logging`, `logger = logging.getLogger(__name__)`, and `delete_document` imported from `src.documents.service`.

- [ ] **Step 4: Run the full suite** — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/intake/router.py tests/test_api.py
git commit -m "fix: roll back upload and return clean 502 when classification fails"
```

---

### Task 4: Document versions + review-ready timestamp

**Files:**
- Modify: `src/documents/models.py`, `src/documents/db.py`, `src/documents/service.py`
- Test: `tests/test_documents.py`

**Interfaces:**
- Produces (Tasks 5–7 consume):
  - `DocumentVersion(SQLModel)`: `id: int | None`, `document_id: int`, `version_number: int`, `text_content: str`, `source_suggestion_id: int | None`, `created_at: datetime`.
  - `Document` gains `review_ready_at: datetime | None = None`.
  - `service.create_version(document_id: int, text_content: str, source_suggestion_id: int | None = None) -> DocumentVersion` (auto-increments `version_number` starting at 1).
  - `service.latest_version(document_id: int) -> DocumentVersion | None`
  - `service.list_versions(document_id: int) -> list[DocumentVersion]` (ascending)
  - `service.get_document(document_id: int) -> Document | None`
  - `service.mark_review_ready(document_id: int) -> None` (sets `review_ready_at = utcnow()`)
  - `db.init_db()` additionally runs an idempotent `ALTER TABLE document ADD COLUMN review_ready_at TIMESTAMP` (needed because `create_all` won't add columns to the existing SQLite table on the Railway volume).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_documents.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, `create_version` undefined.

- [ ] **Step 3: Implement**

`src/documents/models.py` — add to `Document`: `review_ready_at: datetime | None = None`; add:

```python
class DocumentVersion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    version_number: int
    text_content: str
    source_suggestion_id: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
```

`src/documents/db.py` — extend `init_db`:

```python
from sqlalchemy import text as sql_text
from sqlalchemy.exc import OperationalError

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
```

`src/documents/service.py` — add:

```python
def create_version(
    document_id: int, text_content: str, source_suggestion_id: int | None = None
) -> DocumentVersion:
    with db.get_session() as session:
        current = session.exec(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        ).first()
        version = DocumentVersion(
            document_id=document_id,
            version_number=(current.version_number + 1) if current else 1,
            text_content=text_content,
            source_suggestion_id=source_suggestion_id,
        )
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
```

(import `DocumentVersion` in the service's model imports).

- [ ] **Step 4: Run the full suite** — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/documents tests/test_documents.py
git commit -m "feat: immutable document versions and review-ready timestamp"
```

---

### Task 5: Reviewer capability — clause-anchored suggestions

**Files:**
- Create: `src/reviewer/__init__.py`, `src/reviewer/schemas.py`, `src/reviewer/models.py`, `src/reviewer/service.py`
- Test: `tests/test_reviewer.py`

**Interfaces:**
- Consumes: `get_chat_model()`, `create_version`, `latest_version`, `mark_review_ready`, `db.get_session()`.
- Produces (Tasks 6–7 consume):
  - `SuggestionDraft(BaseModel)`: `clause: str`, `original_text: str`, `replacement_text: str`, `rationale: str`.
  - `ReviewResult(BaseModel)`: `suggestions: list[SuggestionDraft]`.
  - `Suggestion(SQLModel)`: `id`, `document_id: int` (indexed), `clause`, `original_text`, `replacement_text`, `rationale`, `status: str = "pending"`, `created_at`.
  - `service.run_review(document_id: int, document_text: str, llm=None) -> list[Suggestion]` — creates version 1 from `document_text` if no version exists, asks the LLM for drafts, **keeps only drafts whose `original_text` occurs exactly once** in `document_text`, persists them, and calls `mark_review_ready` (always — even with zero suggestions).
  - `service.list_suggestions(document_id: int) -> list[Suggestion]`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_reviewer.py`:

```python
from src.classifier.schemas import ClassificationResult  # noqa: F401  (shared fake pattern)
from src.documents.service import latest_version, save_document, get_document
from src.reviewer import service
from src.reviewer.schemas import ReviewResult, SuggestionDraft


class FakeStructuredLLM:
    def __init__(self, result):
        self.result = result
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.result


DOC_TEXT = (
    "Section 1. Term. This agreement lasts 12 months. "
    "Section 2. Liability. Liability is unlimited. "
    "Section 3. Notices. Notices go to legal@acme.com."
)


def _drafts(*pairs):
    return ReviewResult(suggestions=[
        SuggestionDraft(clause=c, original_text=o, replacement_text=r, rationale="why")
        for c, o, r in pairs
    ])


def test_run_review_persists_unique_anchors_and_marks_ready():
    doc = save_document(b"x", "msa.pdf", source="upload")
    fake = FakeStructuredLLM(_drafts(
        ("Section 2", "Liability is unlimited.", "Liability is capped at fees paid."),
        ("Bogus", "text that is not in the document", "irrelevant"),
        ("Dup", "Section", "occurs many times so must be dropped"),
    ))
    suggestions = service.run_review(doc.id, DOC_TEXT, llm=fake)
    assert [s.clause for s in suggestions] == ["Section 2"]
    assert suggestions[0].status == "pending"
    assert DOC_TEXT in fake.prompts[0]
    assert latest_version(doc.id).text_content == DOC_TEXT  # v1 created
    assert get_document(doc.id).review_ready_at is not None


def test_run_review_zero_suggestions_still_marks_ready():
    doc = save_document(b"x", "msa.pdf", source="upload")
    fake = FakeStructuredLLM(_drafts())
    assert service.run_review(doc.id, DOC_TEXT, llm=fake) == []
    assert get_document(doc.id).review_ready_at is not None
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, no `src.reviewer` module.

- [ ] **Step 3: Implement**

`src/reviewer/schemas.py`:

```python
from pydantic import BaseModel


class SuggestionDraft(BaseModel):
    clause: str
    original_text: str
    replacement_text: str
    rationale: str


class ReviewResult(BaseModel):
    suggestions: list[SuggestionDraft]
```

`src/reviewer/models.py`:

```python
from datetime import datetime

from sqlmodel import Field, SQLModel

from src.documents.models import utcnow


class Suggestion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    clause: str
    original_text: str
    replacement_text: str
    rationale: str
    status: str = "pending"  # pending | applied | rejected | stale
    created_at: datetime = Field(default_factory=utcnow)
```

`src/reviewer/service.py`:

```python
from sqlmodel import select

from src.documents import db
from src.documents.service import create_version, latest_version, mark_review_ready
from src.llm.factory import get_chat_model
from src.reviewer.models import Suggestion
from src.reviewer.schemas import ReviewResult

REVIEW_PROMPT = """You are a contract review assistant for a legal-operations team.
Review the contract text below and propose specific redlines that protect our side:
liability caps, termination rights, payment terms, confidentiality, governing law,
ambiguous obligations. Propose only changes that matter.

For each suggestion:
- clause: a short human label for where the change applies (e.g. "Section 2 - Liability").
- original_text: an EXACT, VERBATIM excerpt copied from the contract text that should
  be replaced. It must appear exactly once in the document. Keep it under 300 characters.
- replacement_text: the full replacement for that excerpt.
- rationale: one or two sentences on why.

Contract text:
{document_text}
"""


def run_review(document_id: int, document_text: str, llm=None) -> list[Suggestion]:
    if latest_version(document_id) is None:
        create_version(document_id, document_text)
    llm = llm or get_chat_model()
    result: ReviewResult = llm.with_structured_output(ReviewResult).invoke(
        REVIEW_PROMPT.format(document_text=document_text)
    )
    kept = [d for d in result.suggestions if document_text.count(d.original_text) == 1]
    suggestions = [Suggestion(document_id=document_id, **d.model_dump()) for d in kept]
    with db.get_session() as session:
        for suggestion in suggestions:
            session.add(suggestion)
        session.commit()
        for suggestion in suggestions:
            session.refresh(suggestion)
    mark_review_ready(document_id)
    return suggestions


def list_suggestions(document_id: int) -> list[Suggestion]:
    with db.get_session() as session:
        return list(session.exec(
            select(Suggestion)
            .where(Suggestion.document_id == document_id)
            .order_by(Suggestion.id)
        ))
```

Create empty `src/reviewer/__init__.py`.

- [ ] **Step 4: Run the full suite** — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reviewer tests/test_reviewer.py
git commit -m "feat: reviewer capability with clause-anchored, uniqueness-validated suggestions"
```

---

### Task 6: Auto-review wiring, latency metric, document detail endpoint

**Files:**
- Modify: `src/intake/service.py`, `src/intake/router.py`, `src/documents/schemas.py`, `src/documents/router.py`
- Test: `tests/test_intake.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `run_review`, `list_suggestions` (Task 5); versions API (Task 4).
- Produces:
  - Review runs automatically (rows 8–9): in `process_inbox` and `POST /upload`, when `is_contract_revision` is true, `run_review(doc.id, text)` is called with the same extracted text. Review failures in intake roll back that message like classification failures do (existing try/except already covers it — `run_review` is called inside it). Upload review failure does NOT roll back (the document + classification are valid); it logs and continues — suggestions can be regenerated later.
  - `DocumentOut` gains `review_seconds: float | None` (None until `review_ready_at` set); computed by `_seconds_between(detected_at, review_ready_at)` which strips tzinfo mismatches.
  - `SuggestionOut(BaseModel)`: `id, clause, original_text, replacement_text, rationale, status`.
  - `VersionOut(BaseModel)`: `version_number, source_suggestion_id, created_at`.
  - `DocumentDetailOut(DocumentOut)` adds: `text: str` (latest version text, `""` if none), `suggestions: list[SuggestionOut]`, `versions: list[VersionOut]`.
  - `GET /documents/{document_id}` → `DocumentDetailOut` (404 when missing). Task 7's apply/reject endpoints return this same shape.
  - Module-level helper in `src/documents/schemas.py`: `document_detail(document_id: int) -> DocumentDetailOut` (raises `LookupError` when the document is missing) so Task 7's router can reuse it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py`:

```python
from src.classifier.schemas import ClassificationResult
from src.documents.service import save_document
from src.reviewer.models import Suggestion
from src.reviewer import service as reviewer_service


def test_upload_triggers_review_when_contract_revision(client, monkeypatch):
    calls = []
    monkeypatch.setattr(intake_router, "run_review", lambda doc_id, text, **kw: calls.append((doc_id, text)))
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
```

(Adjust the `client` fixture's monkeypatch of `classify_and_log` to return `is_contract_revision=True` as it already does; also monkeypatch `intake_router.run_review` to a no-op lambda in the fixture so other upload tests don't invoke a real LLM: `monkeypatch.setattr(intake_router, "run_review", lambda *a, **kw: [])`.)

Append to `tests/test_intake.py`:

```python
def test_process_inbox_runs_review_for_contract_revisions(monkeypatch):
    reviewed = []
    monkeypatch.setattr(
        service, "classify_and_log",
        lambda document_id, filename, **kw: ClassificationResult(
            is_contract_revision=True, confidence=0.9, reasoning="stub"),
    )
    monkeypatch.setattr(service, "extract_text_preview", lambda *a, **kw: "TEXT")
    monkeypatch.setattr(service, "run_review", lambda doc_id, text, **kw: reviewed.append(doc_id))
    fake = FakeGmail([_msg("m1", "MSA", [Attachment("msa.docx", b"d")])])
    docs = service.process_inbox(fake)
    assert reviewed == [docs[0].id]
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`run_review` not imported anywhere; `/documents/{id}` route missing).

- [ ] **Step 3: Implement**

`src/intake/service.py` — import `from src.reviewer.service import run_review`; in the loop after `classify_and_log` (capture its result):

```python
            result = classify_and_log(
                doc.id, doc.filename, subject=message.subject,
                body=message.body, document_text=text,
            )
            if result.is_contract_revision:
                run_review(doc.id, text)
```

`src/intake/router.py` — import `run_review`; after successful classification:

```python
    if result.is_contract_revision:
        try:
            run_review(doc.id, text)
        except Exception:
            logger.exception("review failed for %s; suggestions unavailable", doc.filename)
```

`src/documents/schemas.py`:

```python
from datetime import datetime

from pydantic import BaseModel, field_validator

from src.classifier.models import ClassificationLog
from src.documents.models import Document


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    if start.tzinfo:
        start = start.replace(tzinfo=None)
    if end.tzinfo:
        end = end.replace(tzinfo=None)
    return max((end - start).total_seconds(), 0.0)
```

`DocumentOut` gains `review_seconds: float | None = None`; `from_document` passes `review_seconds=_seconds_between(doc.detected_at, doc.review_ready_at)`. Then:

```python
class SuggestionOut(BaseModel):
    id: int
    clause: str
    original_text: str
    replacement_text: str
    rationale: str
    status: str


class VersionOut(BaseModel):
    version_number: int
    source_suggestion_id: int | None
    created_at: datetime


class DocumentDetailOut(DocumentOut):
    text: str
    suggestions: list[SuggestionOut]
    versions: list[VersionOut]


def document_detail(document_id: int) -> DocumentDetailOut:
    from src.classifier.service import get_log
    from src.documents.service import get_document, latest_version, list_versions
    from src.reviewer.service import list_suggestions

    doc = get_document(document_id)
    if doc is None:
        raise LookupError(document_id)
    base = DocumentOut.from_document(doc, get_log(document_id))
    version = latest_version(document_id)
    return DocumentDetailOut(
        **base.model_dump(),
        text=version.text_content if version else "",
        suggestions=[SuggestionOut(**s.model_dump()) for s in list_suggestions(document_id)],
        versions=[VersionOut(**v.model_dump()) for v in list_versions(document_id)],
    )
```

Note: `upload`'s manual `DocumentOut(...)` construction gains nothing — `review_seconds` defaults to `None` (review may still be running; the queue's auto-refresh picks it up).

`src/documents/router.py`:

```python
@router.get("/documents/{document_id}")
def document(document_id: int) -> DocumentDetailOut:
    try:
        return document_detail(document_id)
    except LookupError:
        raise HTTPException(404, "Document not found")
```

(import `HTTPException`, `DocumentDetailOut`, `document_detail`).

- [ ] **Step 4: Run the full suite** — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src tests
git commit -m "feat: automatic review on detection with latency metric and document detail api"
```

---

### Task 7: Redliner — one-click Apply / Reject with versioning

**Files:**
- Create: `src/redliner/__init__.py`, `src/redliner/service.py`, `src/redliner/router.py`
- Modify: `src/main.py` (include router)
- Test: `tests/test_redliner.py`

**Interfaces:**
- Consumes: versions API (Task 4), `Suggestion` (Task 5), `document_detail` (Task 6).
- Produces:
  - `service.apply_suggestion(suggestion_id: int) -> DocumentVersion` — pending-only. Re-anchors against the **latest** version's text: if `original_text` occurs exactly once, replaces it, creates the next version (`source_suggestion_id=suggestion.id`), sets status `applied`. If the anchor no longer occurs exactly once (invalidated by an earlier apply), sets status `stale` and raises `service.StaleAnchorError`. Raises `LookupError` (missing) / `service.AlreadyActionedError` (not pending).
  - `service.reject_suggestion(suggestion_id: int) -> Suggestion` — pending-only; sets status `rejected`; never touches versions. Same error types.
  - `POST /suggestions/{suggestion_id}/apply` and `POST /suggestions/{suggestion_id}/reject` → the updated `DocumentDetailOut`. Errors: 404 missing, 409 already-actioned, 409 stale (detail explains the anchor moved).

- [ ] **Step 1: Write the failing tests** — create `tests/test_redliner.py`:

```python
import pytest
from fastapi.testclient import TestClient

from src.documents import db
from src.documents.service import create_version, latest_version, list_versions, save_document
from src.main import app
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
    doc = save_document(b"x", "msa.pdf", source="upload")
    create_version(doc.id, TEXT)
    return doc


def test_apply_creates_new_version_and_marks_applied():
    doc = _doc_with_text()
    s = _suggestion(doc.id, "Liability is unlimited.", "Liability is capped at fees.")
    version = service.apply_suggestion(s.id)
    assert version.version_number == 2
    assert "Liability is capped at fees." in version.text_content
    assert "Liability is unlimited." not in version.text_content
    assert version.source_suggestion_id == s.id


def test_sequential_applies_and_reject_are_independent():
    doc = _doc_with_text()
    s1 = _suggestion(doc.id, "Term is 12 months.", "Term is 24 months.")
    s2 = _suggestion(doc.id, "Venue is Manila.", "Venue is Singapore.")
    s3 = _suggestion(doc.id, "A. ", "A) ")
    service.apply_suggestion(s1.id)
    service.apply_suggestion(s2.id)
    final = latest_version(doc.id).text_content
    assert "Term is 24 months." in final and "Venue is Singapore." in final
    rejected = service.reject_suggestion(s3.id)
    assert rejected.status == "rejected"
    assert len(list_versions(doc.id)) == 3  # v1 + two applies, reject adds none


def test_stale_anchor_marks_stale_and_raises():
    doc = _doc_with_text()
    s1 = _suggestion(doc.id, "B. Liability is unlimited.", "B. Liability is capped.")
    s2 = _suggestion(doc.id, "Liability is unlimited.", "conflicting change")
    service.apply_suggestion(s1.id)
    with pytest.raises(service.StaleAnchorError):
        service.apply_suggestion(s2.id)
    with db.get_session() as session:
        assert session.get(Suggestion, s2.id).status == "stale"


def test_already_actioned_raises():
    doc = _doc_with_text()
    s = _suggestion(doc.id, "Venue is Manila.", "Venue is Singapore.")
    service.reject_suggestion(s.id)
    with pytest.raises(service.AlreadyActionedError):
        service.apply_suggestion(s.id)


def test_apply_endpoint_returns_detail_and_409s():
    client = TestClient(app)
    doc = _doc_with_text()
    s = _suggestion(doc.id, "Venue is Manila.", "Venue is Singapore.")
    resp = client.post(f"/suggestions/{s.id}/apply")
    assert resp.status_code == 200
    body = resp.json()
    assert "Venue is Singapore." in body["text"]
    assert body["suggestions"][0]["status"] == "applied"
    resp2 = client.post(f"/suggestions/{s.id}/apply")
    assert resp2.status_code == 409
    assert client.post("/suggestions/99999/reject").status_code == 404
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, no `src.redliner`.

- [ ] **Step 3: Implement**

`src/redliner/service.py`:

```python
from src.documents import db
from src.documents.models import DocumentVersion
from src.documents.service import create_version, latest_version
from src.reviewer.models import Suggestion


class AlreadyActionedError(Exception):
    pass


class StaleAnchorError(Exception):
    pass


def _get_pending(session, suggestion_id: int) -> Suggestion:
    suggestion = session.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise LookupError(suggestion_id)
    if suggestion.status != "pending":
        raise AlreadyActionedError(suggestion.status)
    return suggestion


def apply_suggestion(suggestion_id: int) -> DocumentVersion:
    with db.get_session() as session:
        suggestion = _get_pending(session, suggestion_id)
        version = latest_version(suggestion.document_id)
        text = version.text_content if version else ""
        if text.count(suggestion.original_text) != 1:
            suggestion.status = "stale"
            session.add(suggestion)
            session.commit()
            raise StaleAnchorError(suggestion_id)
        suggestion.status = "applied"
        session.add(suggestion)
        session.commit()
        # capture while the session is open — instances detach on exit
        document_id = suggestion.document_id
        new_text = text.replace(suggestion.original_text, suggestion.replacement_text, 1)
    return create_version(document_id, new_text, source_suggestion_id=suggestion_id)


def reject_suggestion(suggestion_id: int) -> Suggestion:
    with db.get_session() as session:
        suggestion = _get_pending(session, suggestion_id)
        suggestion.status = "rejected"
        session.add(suggestion)
        session.commit()
        session.refresh(suggestion)
    return suggestion
```

`src/redliner/router.py`:

```python
from fastapi import APIRouter, HTTPException

from src.documents import db
from src.documents.schemas import DocumentDetailOut, document_detail
from src.redliner.service import (
    AlreadyActionedError,
    StaleAnchorError,
    apply_suggestion,
    reject_suggestion,
)
from src.reviewer.models import Suggestion

router = APIRouter()


def _detail_for(suggestion_id: int) -> DocumentDetailOut:
    with db.get_session() as session:
        suggestion = session.get(Suggestion, suggestion_id)
    return document_detail(suggestion.document_id)


@router.post("/suggestions/{suggestion_id}/apply")
def apply(suggestion_id: int) -> DocumentDetailOut:
    try:
        apply_suggestion(suggestion_id)
    except LookupError:
        raise HTTPException(404, "Suggestion not found")
    except AlreadyActionedError as exc:
        raise HTTPException(409, f"Suggestion already {exc}")
    except StaleAnchorError:
        raise HTTPException(
            409, "This suggestion's text was changed by an earlier applied edit; it is now stale."
        )
    return _detail_for(suggestion_id)


@router.post("/suggestions/{suggestion_id}/reject")
def reject(suggestion_id: int) -> DocumentDetailOut:
    try:
        reject_suggestion(suggestion_id)
    except LookupError:
        raise HTTPException(404, "Suggestion not found")
    except AlreadyActionedError as exc:
        raise HTTPException(409, f"Suggestion already {exc}")
    return _detail_for(suggestion_id)
```

`src/main.py`: `from src.redliner import router as redliner_router` + `app.include_router(redliner_router.router)`.

Create empty `src/redliner/__init__.py`.

- [ ] **Step 4: Run the full suite** — Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/redliner src/main.py tests/test_redliner.py
git commit -m "feat: one-click apply/reject with immutable versioning and stale-anchor safety"
```

---

### Task 8: Locator — clarifying question + Drive confirm/download (rows 5 + 7)

**Files:**
- Modify: `src/locator/schemas.py`, `src/locator/drive_client.py`, `src/locator/router.py`
- Test: `tests/test_locator.py`

**Interfaces:**
- Consumes: `save_document`, `is_supported`, `classify_and_log`, `run_review`, `extract_text_preview`, `document_detail` pattern from Task 6.
- Produces:
  - `GET /drive/search` response becomes `{"results": [...], "clarifying_question": str | None}` — question set **only when len(results) > 1** (row 5): `f"I found {n} contracts matching '{q}'. Which one should I review?"`; `None` for 0 or 1 results.
  - `DriveClient.download(file_id: str, mime_type: str) -> bytes` — Google Docs (`application/vnd.google-apps.document`) via `files().export(fileId=..., mimeType="application/pdf")`, everything else via `files().get_media(fileId=...)` (both `.execute()`).
  - `POST /drive/confirm` body `{"file_id": str, "name": str, "mime_type": str}` → downloads, saves as `source="drive"` (Google Docs get `.pdf` appended to the name), classifies (upload prompt), reviews when revision, logs the confirmed selection (`logger.info("user confirmed drive file %s (%s)", name, file_id)`), returns `DocumentOut` (row 7: selection required before review; logged/displayed).

- [ ] **Step 1: Write the failing tests** — append to `tests/test_locator.py`:

```python
from src.classifier.schemas import ClassificationResult


def test_search_multiple_results_includes_clarifying_question(monkeypatch):
    files = [_file("Acme MSA v3.pdf"), _file("Acme NDA.pdf")]
    monkeypatch.setattr(locator_router, "get_drive_client", lambda: FakeDrive(files))
    resp = TestClient(app).get("/drive/search", params={"q": "acme"})
    body = resp.json()
    assert "Which one should I review?" in body["clarifying_question"]


def test_search_single_result_no_clarifying_question(monkeypatch):
    monkeypatch.setattr(locator_router, "get_drive_client", lambda: FakeDrive([_file("Acme MSA v3.pdf")]))
    body = TestClient(app).get("/drive/search", params={"q": "acme"}).json()
    assert body["clarifying_question"] is None


def test_confirm_downloads_classifies_and_reviews(monkeypatch):
    class FakeDownloader:
        def download(self, file_id, mime_type):
            return b"%PDF-drive-bytes"

    reviewed = []
    monkeypatch.setattr(locator_router, "get_drive_client", lambda: FakeDownloader())
    monkeypatch.setattr(
        locator_router, "classify_and_log",
        lambda document_id, filename, **kw: ClassificationResult(
            is_contract_revision=True, confidence=0.9, reasoning="stub"),
    )
    monkeypatch.setattr(locator_router, "run_review", lambda doc_id, text, **kw: reviewed.append(doc_id))
    resp = TestClient(app).post("/drive/confirm", json={
        "file_id": "f1", "name": "Acme Contract",
        "mime_type": "application/vnd.google-apps.document",
    })
    assert resp.status_code == 201
    assert resp.json()["filename"] == "Acme Contract.pdf"
    assert resp.json()["source"] == "drive"
    assert len(reviewed) == 1
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL (`clarifying_question` missing; no `/drive/confirm`).

- [ ] **Step 3: Implement**

`src/locator/schemas.py` — add:

```python
class SearchResponse(BaseModel):
    results: list[DriveFile]
    clarifying_question: str | None = None


class DriveConfirmRequest(BaseModel):
    file_id: str
    name: str
    mime_type: str
```

`src/locator/drive_client.py` — add constant + method:

```python
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"

    def download(self, file_id: str, mime_type: str) -> bytes:
        if mime_type == GOOGLE_DOC_MIME:
            return self._svc.files().export(
                fileId=file_id, mimeType="application/pdf"
            ).execute()
        return self._svc.files().get_media(fileId=file_id).execute()
```

`src/locator/router.py` — replace the search endpoint and add confirm:

```python
import logging

from fastapi import APIRouter, HTTPException

from src.classifier.service import classify_and_log
from src.documents.extract import FULL_TEXT_MAX_CHARS, extract_text_preview
from src.documents.schemas import DocumentOut
from src.documents.service import is_supported, save_document
from src.locator.drive_client import GOOGLE_DOC_MIME
from src.locator.schemas import DriveConfirmRequest, SearchResponse
from src.locator.service import search_contracts
from src.reviewer.service import run_review

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/drive/search")
def drive_search(q: str) -> SearchResponse:
    results = search_contracts(q, drive=get_drive_client())
    question = (
        f"I found {len(results)} contracts matching '{q}'. Which one should I review?"
        if len(results) > 1 else None
    )
    return SearchResponse(results=results, clarifying_question=question)


@router.post("/drive/confirm", status_code=201)
def drive_confirm(req: DriveConfirmRequest) -> DocumentOut:
    filename = req.name if req.mime_type != GOOGLE_DOC_MIME else f"{req.name}.pdf"
    if not is_supported(filename):
        raise HTTPException(422, "Only PDF, DOCX, or Google Doc files can be reviewed.")
    content = get_drive_client().download(req.file_id, req.mime_type)
    logger.info("user confirmed drive file %s (%s)", req.name, req.file_id)
    doc = save_document(content, filename, source="drive")
    text = extract_text_preview(content, filename, max_chars=FULL_TEXT_MAX_CHARS)
    result = classify_and_log(doc.id, doc.filename, source="upload", document_text=text)
    if result.is_contract_revision:
        run_review(doc.id, text)
    return DocumentOut(
        id=doc.id, filename=doc.filename, source=doc.source,
        mime_type=doc.mime_type, detected_at=doc.detected_at,
        **result.model_dump(),
    )
```

(keep the existing `get_drive_client()` helper; `search_contracts` unchanged; the earlier `dict`-returning search endpoint is replaced — the response model changes shape, which Task 10 mirrors in the frontend).

- [ ] **Step 4: Run the full suite** — Expected: all PASS (the old `test_search_endpoint_empty_result_is_200` asserts `{"results": []}` — update its assertion to `{"results": [], "clarifying_question": None}`).

- [ ] **Step 5: Commit**

```bash
git add src/locator tests/test_locator.py
git commit -m "feat: clarifying question and drive confirm-to-review flow (rows 5, 7)"
```

---

### Task 9: A2A endpoint + agent card

**Files:**
- Create: `src/a2a_server/__init__.py`, `src/a2a_server/agent.py`
- Modify: `src/main.py`, `pyproject.toml`, `requirements.txt`
- Test: `tests/test_a2a.py`

**Interfaces:**
- Produces: the FastAPI app serves the A2A agent card at `GET /a2a/.well-known/agent-card.json` (JSON containing `"name": "Contract Review Agent"` and a `find_contracts` skill), and the A2A JSON-RPC endpoint at `POST /a2a/` which, given a text message, runs a Drive search and replies with a text summary of matches. Spec constraint restated: **the Agent Gateway is Globe's; our boundary is this A2A endpoint.**

> **Version note for the implementer:** `a2a-sdk` is pre-1.0 and its module paths move. The code below targets the current published API. If an import fails, run `.venv\Scripts\pip show a2a-sdk`, read the package README (`https://github.com/a2aproject/a2a-python`), and adapt the imports/builder calls **without changing the two acceptance behaviors** (card served at the path above; message/send returns search-result text). Both are pinned by the tests.

- [ ] **Step 1: Add dependency** — `pyproject.toml` dependencies + `requirements.txt` gain `"a2a-sdk>=0.2"`; run `.venv\Scripts\pip install a2a-sdk`.

- [ ] **Step 2: Write the failing test** — create `tests/test_a2a.py`:

```python
from fastapi.testclient import TestClient

from src.main import app


def test_agent_card_served():
    resp = TestClient(app).get("/a2a/.well-known/agent-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "Contract Review Agent"
    assert any(s["id"] == "find_contracts" for s in card["skills"])
```

- [ ] **Step 3: Run to verify failure** — Expected: 404.

- [ ] **Step 4: Implement** — `src/a2a_server/agent.py`:

```python
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message


class ContractReviewExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        from src.locator.router import get_drive_client
        from src.locator.service import search_contracts

        query = (context.get_user_input() or "").strip()
        if not query:
            await event_queue.enqueue_event(
                new_agent_text_message("Send a keyword to search contracts in Drive.")
            )
            return
        results = search_contracts(query, drive=get_drive_client())
        if not results:
            text = f"No contracts found matching '{query}'."
        else:
            listing = "\n".join(f"- {f.name} (modified {f.modified_time:%Y-%m-%d})" for f in results)
            text = f"Found {len(results)} contract(s) matching '{query}':\n{listing}"
        await event_queue.enqueue_event(new_agent_text_message(text))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


def build_a2a_app():
    card = AgentCard(
        name="Contract Review Agent",
        description="Finds and reviews contract revisions; proposes clause-anchored redlines.",
        url="/a2a/",
        version="0.2.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[AgentSkill(
            id="find_contracts",
            name="Find contracts in Drive",
            description="Keyword search over the authorized Google Drive for contract documents.",
            tags=["contracts", "search"],
        )],
    )
    handler = DefaultRequestHandler(
        agent_executor=ContractReviewExecutor(), task_store=InMemoryTaskStore()
    )
    return A2AStarletteApplication(agent_card=card, http_handler=handler).build()
```

`src/main.py`:

```python
from src.a2a_server.agent import build_a2a_app
app.mount("/a2a", build_a2a_app())
```

Create empty `src/a2a_server/__init__.py`.

- [ ] **Step 5: Run the full suite** — Expected: all PASS. If the card path 404s, list the mounted sub-app's routes (`[r.path for r in app.routes]` via a quick python -c) and adjust the test path to the SDK's served card path under the `/a2a` mount — the card must remain reachable and the test must assert the real path.

- [ ] **Step 6: Commit**

```bash
git add src/a2a_server src/main.py pyproject.toml requirements.txt tests/test_a2a.py
git commit -m "feat: a2a agent card and endpoint (our boundary; gateway is globe's)"
```

---

### Task 10: Frontend — types + API client for Phase 2

**Files (in `D:\SmartWave\contract-review-web`):**
- Modify: `src/types/api.ts`, `src/lib/api.ts`
- Test: `src/lib/api.test.ts`

**Interfaces (consumed by Tasks 12–13):**
- Types: `DocumentOut` gains `review_seconds: number | null`. New: `Suggestion { id: number; clause: string; original_text: string; replacement_text: string; rationale: string; status: 'pending' | 'applied' | 'rejected' | 'stale' }`; `VersionInfo { version_number: number; source_suggestion_id: number | null; created_at: string }`; `DocumentDetail = DocumentOut & { text: string; suggestions: Suggestion[]; versions: VersionInfo[] }`; `DriveSearch { results: DriveFile[]; clarifying_question: string | null }`.
- Functions: `getDocument(id: number): Promise<DocumentDetail>`; `applySuggestion(id: number): Promise<DocumentDetail>`; `rejectSuggestion(id: number): Promise<DocumentDetail>`; `confirmDriveFile(file: DriveFile): Promise<DocumentOut>`; **`searchDrive(q)` now returns `Promise<DriveSearch>`** (whole object — breaking change consumed in Task 13).

- [ ] **Step 1: Write the failing tests** — append to `src/lib/api.test.ts`:

```ts
test('searchDrive returns results and clarifying question', async () => {
  mockFetch(200, { results: [{ file_id: 'f1', name: 'A.pdf' }], clarifying_question: null });
  const search = await searchDrive('acme');
  expect(search.results[0].name).toBe('A.pdf');
  expect(search.clarifying_question).toBeNull();
});

test('applySuggestion posts and returns detail', async () => {
  const stub = mockFetch(200, { id: 1, text: 'new text', suggestions: [], versions: [] });
  const detail = await applySuggestion(5);
  expect(detail.text).toBe('new text');
  expect(vi.mocked(fetch).mock.calls[0][0]).toContain('/suggestions/5/apply');
  expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBe('POST');
});

test('confirmDriveFile posts file identity', async () => {
  mockFetch(201, { id: 9, filename: 'A.pdf' });
  const doc = await confirmDriveFile({
    file_id: 'f1', name: 'A', modified_time: '2026-08-01T00:00:00Z',
    mime_type: 'application/vnd.google-apps.document', web_view_link: null,
  });
  expect(doc.id).toBe(9);
});
```

(update imports; the existing `searchDrive unwraps results` test changes to the new shape.)

- [ ] **Step 2: Run to verify failure** — `npm test` — Expected: FAIL (functions missing / wrong shape).

- [ ] **Step 3: Implement** — `src/types/api.ts` additions as in Interfaces; `src/lib/api.ts`:

```ts
export function searchDrive(q: string): Promise<DriveSearch> {
  return request(`/drive/search?q=${encodeURIComponent(q)}`);
}

export function getDocument(id: number): Promise<DocumentDetail> {
  return request(`/documents/${id}`);
}

export function applySuggestion(id: number): Promise<DocumentDetail> {
  return request(`/suggestions/${id}/apply`, { method: 'POST' });
}

export function rejectSuggestion(id: number): Promise<DocumentDetail> {
  return request(`/suggestions/${id}/reject`, { method: 'POST' });
}

export function confirmDriveFile(file: DriveFile): Promise<DocumentOut> {
  return request('/drive/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_id: file.file_id, name: file.name, mime_type: file.mime_type }),
  });
}
```

- [ ] **Step 4: Run tests + build** — `npm test` and `npm run build` — Expected: both green (Task 13 fixes the SearchPanel compile break if `npm run build` fails here — in that case implement the minimal SearchPanel change from Task 13 Step 3's first snippet now and note it in the commit).

- [ ] **Step 5: Commit**

```bash
git add src/types src/lib
git commit -m "feat: api client for suggestions, document detail, and drive confirm"
```

---

### Task 11: Frontend — drag-and-drop upload

**Files (web repo):**
- Modify: `src/features/upload/upload-form.tsx`
- Test: `src/features/upload/upload-form.test.tsx`

**Interfaces:** none new — the dropzone label gains drag handlers; dropped files pass the same `.pdf`/`.docx` gate as the picker; invalid drops show the existing error line.

- [ ] **Step 1: Write the failing tests** — append to `upload-form.test.tsx`:

```tsx
import { fireEvent } from '@testing-library/react';

test('dropping a pdf selects it', () => {
  render(<UploadForm />);
  const zone = screen.getByText(/choose a contract/i).closest('label')!;
  fireEvent.drop(zone, {
    dataTransfer: { files: [new File(['%PDF'], 'dropped.pdf', { type: 'application/pdf' })] },
  });
  expect(screen.getByText(/dropped\.pdf/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /upload/i })).toBeEnabled();
});

test('dropping an unsupported file shows error and stays disabled', () => {
  render(<UploadForm />);
  const zone = screen.getByText(/choose a contract/i).closest('label')!;
  fireEvent.drop(zone, {
    dataTransfer: { files: [new File(['x'], 'cat.gif', { type: 'image/gif' })] },
  });
  expect(screen.getByText(/PDF or DOCX/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /upload/i })).toBeDisabled();
});
```

- [ ] **Step 2: Run to verify failure** — `npm test` — Expected: FAIL (drop does nothing).

- [ ] **Step 3: Implement** — in `UploadForm`, add state `const [dragging, setDragging] = useState(false);` and a helper:

```tsx
  function takeFile(candidate: File | null) {
    if (!candidate) return;
    if (!/\.(pdf|docx)$/i.test(candidate.name)) {
      setError('Unsupported file type. Upload a PDF or DOCX.');
      setFile(null);
      return;
    }
    setError(null);
    setFile(candidate);
  }
```

Wire the label:

```tsx
        <label
          htmlFor="contract-file"
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); takeFile(e.dataTransfer.files?.[0] ?? null); }}
          className={`flex cursor-pointer flex-col items-center gap-1 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors hover:border-primary hover:bg-surface ${dragging ? 'border-primary bg-surface' : 'border-border'}`}
        >
```

and change the sub-caption to `Click to browse or drag a file here`, the input's `onChange` to `onChange={(e) => takeFile(e.target.files?.[0] ?? null)}`.

- [ ] **Step 4: Run tests + build** — Expected: green (the old click-path tests keep passing; `userEvent.upload` still fires `onChange`).

- [ ] **Step 5: Commit**

```bash
git add src/features/upload
git commit -m "feat: drag-and-drop onto the upload dropzone"
```

---

### Task 12: Frontend — document viewer with Apply/Reject and versions

**Files (web repo):**
- Create: `src/features/document-viewer/document-view.tsx`, `src/features/document-viewer/suggestion-card.tsx`, `src/features/document-viewer/document-view.test.tsx`, `src/app/documents/[id]/page.tsx`
- Test: `src/features/document-viewer/document-view.test.tsx`

**Interfaces:**
- Consumes: `getDocument`, `applySuggestion`, `rejectSuggestion`, `DocumentDetail`, `Suggestion` (Task 10); `Badge`, `Button`, `Card`, `EmptyState` (Phase 1).
- Produces: page at `/documents/{id}`. Document text pane highlights each **pending** suggestion's `original_text` occurrence with `<mark>`; suggestion cards show clause, original → replacement, rationale, status chip, and Apply/Reject buttons (pending only; rows 10–12: distinct controls per suggestion, pending vs actioned visually distinct, rejected marked dismissed — not hidden). Version history list (row 13). Latency chip "Redlines ready in Ns" when `review_seconds` present (row 9).

- [ ] **Step 1: Write the failing tests** — create `document-view.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, test, vi } from 'vitest';
import type { DocumentDetail } from '@/types/api';

const api = { getDocument: vi.fn(), applySuggestion: vi.fn(), rejectSuggestion: vi.fn() };
vi.mock('@/lib/api', () => ({
  getDocument: (...a: unknown[]) => api.getDocument(...a),
  applySuggestion: (...a: unknown[]) => api.applySuggestion(...a),
  rejectSuggestion: (...a: unknown[]) => api.rejectSuggestion(...a),
}));

import { DocumentView } from './document-view';

const detail = (over: Partial<DocumentDetail> = {}): DocumentDetail => ({
  id: 1, filename: 'msa.pdf', source: 'email', mime_type: 'application/pdf',
  detected_at: '2026-08-27T00:00:00Z', is_contract_revision: true,
  confidence: 0.9, reasoning: 'r', review_seconds: 42,
  text: 'Term is 12 months. Liability is unlimited.',
  suggestions: [{
    id: 5, clause: 'Liability', original_text: 'Liability is unlimited.',
    replacement_text: 'Liability is capped.', rationale: 'risk', status: 'pending',
  }],
  versions: [{ version_number: 1, source_suggestion_id: null, created_at: '2026-08-27T00:00:00Z' }],
  ...over,
});

test('renders text, highlighted anchor, latency, and suggestion card', async () => {
  api.getDocument.mockResolvedValue(detail());
  render(<DocumentView documentId={1} />);
  await waitFor(() => expect(screen.getByText(/Term is 12 months/)).toBeInTheDocument());
  expect(screen.getByText('Liability is unlimited.', { selector: 'mark' })).toBeInTheDocument();
  expect(screen.getByText(/ready in 42s/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /apply/i })).toBeInTheDocument();
});

test('apply updates the document and marks suggestion applied', async () => {
  api.getDocument.mockResolvedValue(detail());
  api.applySuggestion.mockResolvedValue(detail({
    text: 'Term is 12 months. Liability is capped.',
    suggestions: [{ ...detail().suggestions[0], status: 'applied' }],
    versions: [...detail().versions, { version_number: 2, source_suggestion_id: 5, created_at: '2026-08-27T00:01:00Z' }],
  }));
  render(<DocumentView documentId={1} />);
  await waitFor(() => screen.getByRole('button', { name: /apply/i }));
  await userEvent.click(screen.getByRole('button', { name: /apply/i }));
  await waitFor(() => expect(screen.getByText(/Liability is capped/)).toBeInTheDocument());
  expect(screen.getByText(/applied/i)).toBeInTheDocument();
  expect(screen.getByText(/v2/i)).toBeInTheDocument();
});

test('rejected suggestion stays visible as dismissed', async () => {
  api.getDocument.mockResolvedValue(detail({
    suggestions: [{ ...detail().suggestions[0], status: 'rejected' }],
  }));
  render(<DocumentView documentId={1} />);
  await waitFor(() => expect(screen.getByText(/rejected/i)).toBeInTheDocument());
  expect(screen.queryByRole('button', { name: /apply/i })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure** — Expected: FAIL, module missing.

- [ ] **Step 3: Implement**

`src/features/document-viewer/suggestion-card.tsx`:

```tsx
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import type { Suggestion } from '@/types/api';

const tones = { pending: 'warning', applied: 'success', rejected: 'neutral', stale: 'danger' } as const;

export function SuggestionCard({
  suggestion,
  busy,
  onApply,
  onReject,
}: {
  suggestion: Suggestion;
  busy: boolean;
  onApply: () => void;
  onReject: () => void;
}) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold">{suggestion.clause}</p>
        <Badge tone={tones[suggestion.status]}>{suggestion.status}</Badge>
      </div>
      <p className="text-sm text-text-muted line-through">{suggestion.original_text}</p>
      <p className="text-sm">{suggestion.replacement_text}</p>
      <p className="text-xs text-text-muted">{suggestion.rationale}</p>
      {suggestion.status === 'pending' && (
        <div className="mt-1 flex gap-2">
          <Button onClick={onApply} disabled={busy}>Apply</Button>
          <Button variant="secondary" onClick={onReject} disabled={busy}>Reject</Button>
        </div>
      )}
    </Card>
  );
}
```

`src/features/document-viewer/document-view.tsx`:

```tsx
'use client';

import { useCallback, useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { applySuggestion, getDocument, rejectSuggestion } from '@/lib/api';
import type { DocumentDetail } from '@/types/api';
import { SuggestionCard } from './suggestion-card';

function highlight(text: string, anchors: string[]) {
  let segments: (string | { mark: string })[] = [text];
  for (const anchor of anchors) {
    segments = segments.flatMap((seg) => {
      if (typeof seg !== 'string' || !seg.includes(anchor)) return [seg];
      const [before, ...rest] = seg.split(anchor);
      return [before, { mark: anchor }, rest.join(anchor)];
    });
  }
  return segments.map((seg, i) =>
    typeof seg === 'string' ? (
      <span key={i}>{seg}</span>
    ) : (
      <mark key={i} className="rounded bg-warning/20 px-0.5">{seg.mark}</mark>
    ),
  );
}

export function DocumentView({ documentId }: { documentId: number }) {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getDocument(documentId).then(setDetail).catch((e) =>
      setError(e instanceof Error ? e.message : 'Failed to load document'));
  }, [documentId]);

  const act = useCallback(async (fn: (id: number) => Promise<DocumentDetail>, id: number) => {
    setBusy(true);
    setError(null);
    try {
      setDetail(await fn(id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed');
      setDetail(await getDocument(documentId));
    } finally {
      setBusy(false);
    }
  }, [documentId]);

  if (error && !detail) return <EmptyState title="Could not load document" description={error} />;
  if (!detail) return <p className="text-sm text-text-muted">Loading…</p>;

  const pendingAnchors = detail.suggestions
    .filter((s) => s.status === 'pending')
    .map((s) => s.original_text);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{detail.filename}</h1>
        {detail.review_seconds !== null && (
          <Badge tone="success">redlines ready in {Math.round(detail.review_seconds)}s</Badge>
        )}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
      <div className="grid gap-6 md:grid-cols-[1fr_340px]">
        <Card className="whitespace-pre-wrap text-sm leading-7">
          {detail.text ? highlight(detail.text, pendingAnchors) : 'No text extracted for this document.'}
        </Card>
        <div className="flex flex-col gap-3">
          <p className="text-sm font-semibold">Suggested redlines ({detail.suggestions.length})</p>
          {detail.suggestions.length === 0 && (
            <p className="text-sm text-text-muted">No suggestions for this document.</p>
          )}
          {detail.suggestions.map((s) => (
            <SuggestionCard
              key={s.id}
              suggestion={s}
              busy={busy}
              onApply={() => act(applySuggestion, s.id)}
              onReject={() => act(rejectSuggestion, s.id)}
            />
          ))}
          <p className="mt-2 text-sm font-semibold">Versions</p>
          <ul className="flex flex-col gap-1 text-sm text-text-muted">
            {detail.versions.map((v) => (
              <li key={v.version_number}>
                v{v.version_number} · {new Date(v.created_at).toLocaleString()}
                {v.source_suggestion_id ? ` · from suggestion #${v.source_suggestion_id}` : ' · original'}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
```

`src/app/documents/[id]/page.tsx`:

```tsx
import { DocumentView } from '@/features/document-viewer/document-view';

export default async function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <main className="mx-auto max-w-5xl px-6 py-10 sm:px-8">
      <DocumentView documentId={Number(id)} />
    </main>
  );
}
```

- [ ] **Step 4: Run tests + build** — `npm test` and `npm run build` — Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/features/document-viewer src/app/documents
git commit -m "feat: document viewer with apply/reject, highlights, and version history"
```

---

### Task 13: Frontend — queue links + search clarifying/confirm flow

**Files (web repo):**
- Modify: `src/features/review-queue/document-list.tsx`, `src/features/drive-search/search-panel.tsx`
- Test: `src/features/review-queue/document-list.test.tsx`, `src/features/drive-search/search-panel.test.tsx`

**Interfaces:**
- Consumes: `searchDrive` (new `DriveSearch` shape), `confirmDriveFile` (Task 10); `/documents/{id}` route (Task 12).
- Produces: queue cards link to `/documents/{id}` and show a "redlines ready · Ns" chip when `review_seconds` non-null; search panel renders the clarifying question banner when present (row 5), and each result gains a **Review** button that confirms the file (row 7) then navigates to the new document via `window.location.assign('/documents/' + doc.id)` (plain assign keeps the component free of router mocking in tests).

- [ ] **Step 1: Write the failing tests**

Append to `document-list.test.tsx`:

```tsx
test('card links to document page and shows latency chip', () => {
  render(<DocumentList documents={[doc({ review_seconds: 42 })]} />);
  expect(screen.getByRole('link', { name: /msa-v2\.docx/i })).toHaveAttribute('href', '/documents/1');
  expect(screen.getByText(/redlines ready · 42s/i)).toBeInTheDocument();
});
```

(the `doc()` factory gains `review_seconds: null` in its defaults.)

Append to `search-panel.test.tsx` (update existing mocks to the `DriveSearch` shape — `searchDrive.mockResolvedValue({ results: [...], clarifying_question: null })`):

```tsx
const confirmDriveFile = vi.fn();
// add to the vi.mock factory: confirmDriveFile: (...a: unknown[]) => confirmDriveFile(...a)

test('clarifying question shown for multiple results', async () => {
  searchDrive.mockResolvedValue({
    results: [file('Acme MSA.pdf'), file('Acme NDA.pdf')],
    clarifying_question: "I found 2 contracts matching 'acme'. Which one should I review?",
  });
  render(<SearchPanel />);
  await userEvent.type(screen.getByRole('searchbox'), 'acme');
  await userEvent.click(screen.getByRole('button', { name: /search/i }));
  await waitFor(() =>
    expect(screen.getByText(/which one should i review/i)).toBeInTheDocument());
});

test('review button confirms the file', async () => {
  searchDrive.mockResolvedValue({ results: [file('Acme MSA.pdf')], clarifying_question: null });
  confirmDriveFile.mockResolvedValue({ id: 9 });
  render(<SearchPanel />);
  await userEvent.type(screen.getByRole('searchbox'), 'acme');
  await userEvent.click(screen.getByRole('button', { name: /search/i }));
  await waitFor(() => screen.getByRole('button', { name: /^review$/i }));
  await userEvent.click(screen.getByRole('button', { name: /^review$/i }));
  await waitFor(() => expect(confirmDriveFile).toHaveBeenCalled());
});
```

(`file(name)` = the existing `_file`-style factory local to the test.)

- [ ] **Step 2: Run to verify failure** — Expected: FAIL.

- [ ] **Step 3: Implement**

`document-list.tsx`: wrap each card's filename in `<a href={'/documents/' + doc.id} className="truncate font-medium hover:underline">{doc.filename}</a>` and add next to the confidence span:

```tsx
              {doc.review_seconds !== null && (
                <Badge tone="success">redlines ready · {Math.round(doc.review_seconds)}s</Badge>
              )}
```

`search-panel.tsx`: state `const [search, setSearch] = useState<DriveSearch | null>(null);` replaces `results` (update render references to `search.results` / `search.clarifying_question`); after results load, render the banner:

```tsx
      {search?.clarifying_question && (
        <p className="rounded-md bg-warning/10 px-3 py-2 text-sm text-warning">
          {search.clarifying_question}
        </p>
      )}
```

Each result card gains, next to "Open in Drive":

```tsx
                  <Button
                    onClick={async () => {
                      setBusy(true);
                      setError(null);
                      try {
                        const doc = await confirmDriveFile(file);
                        window.location.assign(`/documents/${doc.id}`);
                      } catch (e) {
                        setError(e instanceof Error ? e.message : 'Could not start review');
                      } finally {
                        setBusy(false);
                      }
                    }}
                    disabled={busy}
                  >
                    Review
                  </Button>
```

- [ ] **Step 4: Run tests + build** — Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/features/review-queue src/features/drive-search
git commit -m "feat: queue links, latency chips, clarifying question, and drive review flow"
```

---

### Task 14: Docs — limitations + deployment notes

**Files:**
- Modify: `docs/limitations.md`, `docs/deployment.md` (backend repo)

**Interfaces:** none — bookkeeping so the tracker/demo story stays honest.

- [ ] **Step 1: Update `docs/limitations.md`**: check the four fixed boxes (content-aware classifier, full email body, upload rollback, drag-and-drop) with a `(fixed 2026-08-27, Phase 2)` note; under "Deferred by plan", check rows 5, 7–13 and the A2A endpoint as shipped; row 14 note becomes "917 output format: proceeding with new-version-per-apply per Ryan 2026-08-27 — confirm before Sept 7". Add one new known limitation: "Review quality is ungrounded (no RAG yet) — suggestions come from general legal knowledge until Phase 3's legal-document pool."

- [ ] **Step 2: Update `docs/deployment.md`**: note that a redeploy after this phase runs an additive SQLite migration automatically (`review_ready_at` column) — no manual step; and that `/a2a/.well-known/agent-card.json` should load on Railway as a post-deploy check.

- [ ] **Step 3: Commit**

```bash
git add docs
git commit -m "docs: phase 2 limitations and deployment notes"
```

---

## Out of scope (Phase 3, before Sept 7)

RAG grounding over the legal-document pool (corpus source still unconfirmed), gateway mock, demo-account switch for the poller, tracked-changes DOCX export (only if 917 reverses), demo polish.

## Open questions carried

1. 917 confirmation of new-version-per-apply (proceeding per Ryan 2026-08-27; row 14 acceptance still needs their explicit yes).
2. RAG corpus source (blocks Phase 3).
