# Revision Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a contract revision arrives, find the most similar prior contract in the DB, LLM-compare the two, and show validated change highlights in a new "Compared with prior" viewer tab.

**Architecture:** New `comparator` capability module in the Python agent repo (router/schemas/service/models, matching the other capability modules), triggered best-effort after `run_review` in both intake seams. Two LLM calls (match, then compare) via the existing `get_chat_model()` factory, with excerpt anchors validated by `text.count(excerpt) == 1` before persisting. The Next.js web repo gets a third viewer tab that fetches `GET /documents/{id}/comparison` lazily.

**Tech Stack:** FastAPI + SQLModel/SQLite + LangChain structured output (agent repo, tests: `.venv/bin/python -m pytest`); Next.js 16 + Tailwind 4 (web repo, tests: `npm test`).

**Spec:** `docs/superpowers/specs/2026-09-01-revision-comparison-design.md` (agent repo). Read it before starting.

## Global Constraints

- Two git repos: agent = `/home/penaj/dev/smartwave/contract-review/contract-review-agent`, web = `/home/penaj/dev/smartwave/contract-review/contract-review-web`. Tasks 1–4 commit in the agent repo, Tasks 5–7 in the web repo.
- Commits must be authored as `ryan-smartwave <ryan@smartwave.ph>` — verify with `git config user.email` before the first commit in each repo.
- Model calls ONLY via `src.llm.factory.get_chat_model()` — never a vendor SDK directly. Every service function takes an `llm=None` param overridable in tests (see `src/reviewer/service.py:run_review` for the pattern).
- Comparison must NEVER block or fail intake, classification, or review.
- Status strings exactly: `"ready"`, `"no_match"`, `"failed"` stored; `"pending"` is the API's word for "no row yet".
- Change kinds exactly: `"added"`, `"removed"`, `"modified"`.
- Agent tests run with `.venv/bin/python -m pytest` (no global pytest). Web tests with `npm test`, lint check with `npx eslint src`.

---

### Task 1: Comparator models, schemas, and similar-contract matching

**Files:**
- Create: `src/comparator/__init__.py` (empty)
- Create: `src/comparator/models.py`
- Create: `src/comparator/schemas.py`
- Create: `src/comparator/service.py`
- Test: `tests/test_comparator.py`

**Interfaces:**
- Consumes: `src.documents.service.list_documents()`, `latest_version(document_id)`, `src.documents.models.utcnow`, `src.llm.factory.get_chat_model`.
- Produces: `Comparison` / `ComparisonChange` SQLModel tables; `MatchResult`, `ChangeDraft`, `CompareResult` pydantic schemas; `select_match(document_id, document_text, llm) -> tuple[int | None, str]` returning `(matched_document_id, matched_text)` where `matched_text` is the matched doc's latest version text (empty string when no match).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_comparator.py`:

```python
from src.comparator import service
from src.comparator.schemas import ChangeDraft, CompareResult, MatchResult
from src.documents.service import create_version, save_document


class FakeStructuredLLM:
    """Returns queued results in order; records prompts (same pattern as test_reviewer)."""

    def __init__(self, *results):
        self.results = list(results)
        self.prompts = []

    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


NEW_TEXT = "Section 1. Term is 24 months. Section 2. Liability is capped at fees."
OLD_TEXT = "Section 1. Term is 12 months. Section 2. Liability is unlimited."


def _prior_doc(text=OLD_TEXT, filename="msa-2025.pdf"):
    doc = save_document(b"x", filename, source="upload")
    create_version(doc.id, text)
    return doc


def test_select_match_returns_none_when_no_other_documents():
    doc = save_document(b"x", "new.pdf", source="upload")
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=None)
    assert matched_id is None
    assert matched_text == ""


def test_select_match_picks_candidate_and_returns_its_text():
    prior = _prior_doc()
    doc = save_document(b"x", "msa-2026.pdf", source="upload")
    fake = FakeStructuredLLM(MatchResult(matched_document_id=prior.id, reason="same MSA"))
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=fake)
    assert matched_id == prior.id
    assert matched_text == OLD_TEXT
    # the prompt offered the candidate and the new document
    assert "msa-2025.pdf" in fake.prompts[0]
    assert "msa-2026.pdf" in fake.prompts[0]


def test_select_match_excludes_self_and_versionless_docs():
    no_version = save_document(b"x", "empty.pdf", source="upload")  # noqa: F841
    doc = save_document(b"x", "new.pdf", source="upload")
    create_version(doc.id, NEW_TEXT)  # its own version must not make it a candidate
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=None)
    assert matched_id is None
    assert matched_text == ""


def test_select_match_llm_none_answer_means_no_match():
    _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(MatchResult(matched_document_id=None, reason="unrelated"))
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=fake)
    assert matched_id is None
    assert matched_text == ""


def test_select_match_hallucinated_id_means_no_match():
    _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(MatchResult(matched_document_id=99999, reason="made up"))
    matched_id, matched_text = service.select_match(doc.id, NEW_TEXT, llm=fake)
    assert matched_id is None
    assert matched_text == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_comparator.py -q`
Expected: import errors / `AttributeError` — `src.comparator` does not exist yet. (`ModuleNotFoundError: No module named 'src.comparator'`)

- [ ] **Step 3: Write the implementation**

`src/comparator/__init__.py`: empty file.

`src/comparator/models.py`:

```python
from datetime import datetime

from sqlmodel import Field, SQLModel

from src.documents.models import utcnow


class Comparison(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(index=True)
    matched_document_id: int | None = None
    status: str  # "ready" | "no_match" | "failed"
    summary: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ComparisonChange(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    comparison_id: int = Field(index=True)
    kind: str  # "added" | "removed" | "modified"
    clause: str
    before_text: str | None = None
    after_text: str | None = None
    note: str
```

`src/comparator/schemas.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


# --- LLM structured output ---

class MatchResult(BaseModel):
    matched_document_id: int | None
    reason: str


class ChangeDraft(BaseModel):
    kind: Literal["added", "removed", "modified"]
    clause: str
    before_text: str | None = None
    after_text: str | None = None
    note: str


class CompareResult(BaseModel):
    summary: str
    changes: list[ChangeDraft]


# --- API output ---

class MatchedDocumentOut(BaseModel):
    id: int
    filename: str
    detected_at: datetime


class ChangeOut(BaseModel):
    kind: str
    clause: str
    before_text: str | None
    after_text: str | None
    note: str


class ComparisonOut(BaseModel):
    status: str  # "pending" | "ready" | "no_match" | "failed"
    matched_document: MatchedDocumentOut | None = None
    summary: str | None = None
    changes: list[ChangeOut] = []
```

`src/comparator/service.py` (Task 2 extends this file; this task creates it with matching only):

```python
import logging

from src.comparator.schemas import MatchResult
from src.documents.extract import FULL_TEXT_MAX_CHARS
from src.documents.service import latest_version, list_documents
from src.llm.factory import get_chat_model

logger = logging.getLogger(__name__)

MATCH_PROMPT = """You are matching a newly received contract against a database
of prior contracts to find the most similar one (an earlier version, the same
counterparty, or the same agreement type).

New document: {filename}
Beginning of its text:
{new_snippet}

Candidates:
{candidates}

Reply with the id of the single most similar candidate, or null if none is
plausibly related to the new document.
"""


def _candidates(document_id: int) -> list[tuple[int, str, str]]:
    """(id, filename, latest version text) for every other document with a version."""
    out = []
    for doc in list_documents():
        if doc.id == document_id:
            continue
        version = latest_version(doc.id)
        if version is None:
            continue
        out.append((doc.id, doc.filename, version.text_content))
    return out


def select_match(document_id: int, document_text: str, llm=None) -> tuple[int | None, str]:
    candidates = _candidates(document_id)
    if not candidates:
        return None, ""
    from src.documents.service import get_document

    doc = get_document(document_id)
    candidate_lines = "\n".join(
        f"- id={cid} filename={fname}\n  {text[:500]}" for cid, fname, text in candidates
    )
    llm = llm or get_chat_model()
    result: MatchResult = llm.with_structured_output(MatchResult).invoke(
        MATCH_PROMPT.format(
            filename=doc.filename if doc else "unknown",
            new_snippet=document_text[:1500],
            candidates=candidate_lines,
        )
    )
    by_id = {cid: text for cid, _, text in candidates}
    if result.matched_document_id in by_id:
        return result.matched_document_id, by_id[result.matched_document_id]
    return None, ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_comparator.py -q`
Expected: 5 passed. Then run the full suite: `.venv/bin/python -m pytest tests/ -q` — everything passes (new tables are registered on SQLModel metadata via import; the conftest fixture `create_all`s them only if the module is imported, which the test file does).

- [ ] **Step 5: Commit**

```bash
git add src/comparator tests/test_comparator.py
git commit -m "feat: comparator matching — pick the most similar prior contract"
```

---

### Task 2: run_comparison — LLM compare, anchor validation, persistence

**Files:**
- Modify: `src/comparator/service.py` (append)
- Test: `tests/test_comparator.py` (append)

**Interfaces:**
- Consumes: `select_match` from Task 1; `Comparison`/`ComparisonChange` models; `CompareResult`/`ChangeDraft` schemas; `src.documents.db.get_session`.
- Produces: `run_comparison(document_id: int, document_text: str, llm=None) -> Comparison` (never raises); `get_comparison(document_id: int) -> tuple[Comparison, list[ComparisonChange]] | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_comparator.py`:

```python
from src.comparator.models import Comparison, ComparisonChange  # top of file
from src.documents import db  # top of file


def _compare_result(*changes, summary="Liability and term changed."):
    return CompareResult(summary=summary, changes=list(changes))


def test_run_comparison_no_candidates_stores_no_match():
    doc = save_document(b"x", "new.pdf", source="upload")
    comparison = service.run_comparison(doc.id, NEW_TEXT, llm=None)
    assert comparison.status == "no_match"
    assert comparison.matched_document_id is None


def test_run_comparison_happy_path_persists_summary_and_valid_changes():
    prior = _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(
        MatchResult(matched_document_id=prior.id, reason="same MSA"),
        _compare_result(
            ChangeDraft(kind="modified", clause="Term",
                        before_text="Term is 12 months.", after_text="Term is 24 months.",
                        note="Term doubled."),
            ChangeDraft(kind="added", clause="Fabricated",
                        before_text=None, after_text="text not present in the new document",
                        note="hallucinated"),
            ChangeDraft(kind="removed", clause="Also fabricated",
                        before_text="text not present in the old document", after_text=None,
                        note="hallucinated"),
        ),
    )
    comparison = service.run_comparison(doc.id, NEW_TEXT, llm=fake)
    assert comparison.status == "ready"
    assert comparison.matched_document_id == prior.id
    assert comparison.summary == "Liability and term changed."
    stored = service.get_comparison(doc.id)
    assert stored is not None
    _, changes = stored
    assert [c.clause for c in changes] == ["Term"]  # both fabricated anchors dropped
    # both texts reached the compare prompt
    assert NEW_TEXT in fake.prompts[1] and OLD_TEXT in fake.prompts[1]


def test_run_comparison_modified_requires_both_anchors():
    prior = _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(
        MatchResult(matched_document_id=prior.id, reason="same"),
        _compare_result(
            ChangeDraft(kind="modified", clause="Half-anchored",
                        before_text="not in old text", after_text="Term is 24 months.",
                        note="before anchor bad"),
        ),
    )
    service.run_comparison(doc.id, NEW_TEXT, llm=fake)
    _, changes = service.get_comparison(doc.id)
    assert changes == []


def test_run_comparison_llm_failure_stores_failed_and_does_not_raise():
    _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(RuntimeError("provider down"))
    comparison = service.run_comparison(doc.id, NEW_TEXT, llm=fake)
    assert comparison.status == "failed"
    stored, changes = service.get_comparison(doc.id)
    assert stored.status == "failed"
    assert changes == []


def test_get_comparison_returns_none_before_any_run():
    doc = save_document(b"x", "new.pdf", source="upload")
    assert service.get_comparison(doc.id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_comparator.py -q`
Expected: the 5 new tests FAIL with `AttributeError: module 'src.comparator.service' has no attribute 'run_comparison'`; Task 1's 5 still pass.

- [ ] **Step 3: Write the implementation**

Append to `src/comparator/service.py`:

```python
from sqlmodel import select

from src.comparator.models import Comparison, ComparisonChange
from src.comparator.schemas import ChangeDraft, CompareResult
from src.documents import db

COMPARE_PROMPT = """You are comparing a newly received contract against the most
similar prior contract from our database. Identify what changed.

For each change:
- kind: "added" (new clause/text), "removed" (present before, gone now), or
  "modified" (present in both, altered).
- clause: a short human label (e.g. "Section 4 - Liability").
- before_text: an EXACT, VERBATIM excerpt from the PRIOR contract (required for
  removed and modified; null for added). It must appear exactly once in the
  prior contract, must not span a blank line, and must stay under 300 characters.
- after_text: an EXACT, VERBATIM excerpt from the NEW contract (required for
  added and modified; null for removed). Same rules against the new contract.
- note: one sentence on what the change does.

Also write a 2-4 sentence summary of the overall differences.

PRIOR contract:
{old_text}

NEW contract:
{new_text}
"""


def _anchored(change: ChangeDraft, new_text: str, old_text: str) -> bool:
    needs_after = change.kind in ("added", "modified")
    needs_before = change.kind in ("removed", "modified")
    if needs_after and not (change.after_text and new_text.count(change.after_text) == 1):
        return False
    if needs_before and not (change.before_text and old_text.count(change.before_text) == 1):
        return False
    return True


def _store(document_id: int, status: str, matched_document_id: int | None = None,
           summary: str | None = None, changes: list[ChangeDraft] | None = None) -> Comparison:
    with db.get_session() as session:
        comparison = Comparison(
            document_id=document_id, matched_document_id=matched_document_id,
            status=status, summary=summary,
        )
        session.add(comparison)
        session.commit()
        session.refresh(comparison)
        for change in changes or []:
            session.add(ComparisonChange(comparison_id=comparison.id, **change.model_dump()))
        session.commit()
        session.refresh(comparison)
    return comparison


def run_comparison(document_id: int, document_text: str, llm=None) -> Comparison:
    try:
        matched_id, old_text = select_match(document_id, document_text, llm=llm)
        if matched_id is None:
            return _store(document_id, "no_match")
        new_text = document_text[:FULL_TEXT_MAX_CHARS]
        old_text = old_text[:FULL_TEXT_MAX_CHARS]
        model = llm or get_chat_model()
        result: CompareResult = model.with_structured_output(CompareResult).invoke(
            COMPARE_PROMPT.format(old_text=old_text, new_text=new_text)
        )
        kept = [c for c in result.changes if _anchored(c, new_text, old_text)]
        return _store(document_id, "ready", matched_document_id=matched_id,
                      summary=result.summary, changes=kept)
    except Exception:
        logger.exception("comparison failed for document %s", document_id)
        return _store(document_id, "failed")


def get_comparison(document_id: int) -> tuple[Comparison, list[ComparisonChange]] | None:
    with db.get_session() as session:
        comparison = session.exec(
            select(Comparison)
            .where(Comparison.document_id == document_id)
            .order_by(Comparison.id.desc())
        ).first()
        if comparison is None:
            return None
        changes = list(session.exec(
            select(ComparisonChange)
            .where(ComparisonChange.comparison_id == comparison.id)
            .order_by(ComparisonChange.id)
        ))
    return comparison, changes
```

Note: `select_match` is called inside the try, so a match-stage LLM failure also lands in `"failed"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_comparator.py -q` → 10 passed.
Then full suite: `.venv/bin/python -m pytest tests/ -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/comparator/service.py tests/test_comparator.py
git commit -m "feat: run_comparison — LLM compare with validated anchors, persisted"
```

---

### Task 3: Comparison endpoint

**Files:**
- Create: `src/comparator/router.py`
- Modify: `src/main.py` (register router)
- Test: `tests/test_comparator.py` (append)

**Interfaces:**
- Consumes: `get_comparison` (Task 2), `ComparisonOut`/`MatchedDocumentOut`/`ChangeOut` (Task 1), `src.documents.service.get_document`.
- Produces: `GET /documents/{document_id}/comparison` → `ComparisonOut` (shape consumed by web Task 5).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_comparator.py` (add `from fastapi.testclient import TestClient` and `from src.main import app` at the top):

```python
def test_comparison_endpoint_404_for_missing_document():
    client = TestClient(app)
    assert client.get("/documents/99999/comparison").status_code == 404


def test_comparison_endpoint_pending_before_any_run():
    client = TestClient(app)
    doc = save_document(b"x", "new.pdf", source="upload")
    body = client.get(f"/documents/{doc.id}/comparison").json()
    assert body == {"status": "pending", "matched_document": None, "summary": None, "changes": []}


def test_comparison_endpoint_ready_includes_match_summary_and_changes():
    prior = _prior_doc()
    doc = save_document(b"x", "new.pdf", source="upload")
    fake = FakeStructuredLLM(
        MatchResult(matched_document_id=prior.id, reason="same"),
        _compare_result(
            ChangeDraft(kind="modified", clause="Term",
                        before_text="Term is 12 months.", after_text="Term is 24 months.",
                        note="Term doubled."),
        ),
    )
    service.run_comparison(doc.id, NEW_TEXT, llm=fake)
    body = TestClient(app).get(f"/documents/{doc.id}/comparison").json()
    assert body["status"] == "ready"
    assert body["matched_document"]["id"] == prior.id
    assert body["matched_document"]["filename"] == "msa-2025.pdf"
    assert body["summary"] == "Liability and term changed."
    assert body["changes"] == [{
        "kind": "modified", "clause": "Term",
        "before_text": "Term is 12 months.", "after_text": "Term is 24 months.",
        "note": "Term doubled.",
    }]


def test_comparison_endpoint_no_match_and_failed_have_empty_changes():
    doc = save_document(b"x", "new.pdf", source="upload")
    service.run_comparison(doc.id, NEW_TEXT, llm=None)  # no candidates -> no_match
    body = TestClient(app).get(f"/documents/{doc.id}/comparison").json()
    assert body["status"] == "no_match"
    assert body["matched_document"] is None
    assert body["changes"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_comparator.py -q`
Expected: the 4 new tests FAIL with 404s that have the wrong shape / missing route (`assert 404 == ...` on the pending test — FastAPI returns 404 `{"detail": "Not Found"}` for the unregistered path).

- [ ] **Step 3: Write the implementation**

`src/comparator/router.py`:

```python
from fastapi import APIRouter, HTTPException

from src.comparator.schemas import ChangeOut, ComparisonOut, MatchedDocumentOut
from src.comparator.service import get_comparison
from src.documents.service import get_document

router = APIRouter()


@router.get("/documents/{document_id}/comparison")
def comparison(document_id: int) -> ComparisonOut:
    if get_document(document_id) is None:
        raise HTTPException(404, "Document not found")
    stored = get_comparison(document_id)
    if stored is None:
        return ComparisonOut(status="pending")
    record, changes = stored
    matched = get_document(record.matched_document_id) if record.matched_document_id else None
    return ComparisonOut(
        status=record.status,
        matched_document=(
            MatchedDocumentOut(id=matched.id, filename=matched.filename,
                               detected_at=matched.detected_at)
            if matched else None
        ),
        summary=record.summary,
        changes=[ChangeOut(kind=c.kind, clause=c.clause, before_text=c.before_text,
                           after_text=c.after_text, note=c.note) for c in changes],
    )
```

In `src/main.py`, add the import next to the other routers and register it:

```python
from src.comparator.router import router as comparator_router
```

```python
app.include_router(comparator_router)
```

(Place `include_router` with the existing ones, before `app.mount("/a2a", ...)`. This import also guarantees the comparator tables are on SQLModel metadata before `init_db()` runs in production.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/comparator/router.py src/main.py tests/test_comparator.py
git commit -m "feat: GET /documents/{id}/comparison endpoint"
```

---

### Task 4: Trigger comparison from both intake seams

**Files:**
- Modify: `src/intake/pipeline.py` (upload/Drive seam — after `run_review` inside `ingest_document`)
- Modify: `src/intake/service.py` (email seam — after `run_review` inside `process_inbox`)
- Modify: `docs/limitations.md` (flip the revision-comparison row to shipped; add no-retry row)
- Test: `tests/test_comparator.py` (append)

**Interfaces:**
- Consumes: `run_comparison(document_id, document_text)` from Task 2.
- Produces: comparison rows exist automatically for every document classified as a contract revision.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_comparator.py` (add `from src.classifier.schemas import ClassificationResult` and `from src.intake import pipeline` at the top):

```python
def _classified(is_revision=True):
    return ClassificationResult(
        is_contract_revision=is_revision, confidence=0.9, reasoning="r"
    )


def test_ingest_document_triggers_comparison_for_revisions(monkeypatch):
    monkeypatch.setattr(pipeline, "classify_and_log", lambda *a, **kw: _classified())
    monkeypatch.setattr(pipeline, "run_review", lambda *a, **kw: [])
    calls = []
    monkeypatch.setattr(pipeline, "run_comparison", lambda doc_id, text: calls.append((doc_id, text)))
    doc, _ = pipeline.ingest_document(b"%PDF-1.4 fake", "new.pdf", source="upload")
    assert calls and calls[0][0] == doc.id


def test_ingest_document_skips_comparison_for_non_revisions(monkeypatch):
    monkeypatch.setattr(pipeline, "classify_and_log", lambda *a, **kw: _classified(is_revision=False))
    calls = []
    monkeypatch.setattr(pipeline, "run_comparison", lambda *a, **kw: calls.append(a))
    pipeline.ingest_document(b"%PDF-1.4 fake", "new.pdf", source="upload")
    assert calls == []


def test_ingest_document_survives_comparison_failure(monkeypatch):
    monkeypatch.setattr(pipeline, "classify_and_log", lambda *a, **kw: _classified())
    monkeypatch.setattr(pipeline, "run_review", lambda *a, **kw: [])

    def boom(*a, **kw):
        raise RuntimeError("comparison exploded")

    monkeypatch.setattr(pipeline, "run_comparison", boom)
    doc, result = pipeline.ingest_document(b"%PDF-1.4 fake", "new.pdf", source="upload")
    assert doc.id is not None  # intake succeeded anyway
```

(`ClassificationResult` fields: check `src/classifier/schemas.py` if the constructor above errors — use its actual required fields.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_comparator.py -q`
Expected: the first test FAILS with `AttributeError: <module 'src.intake.pipeline'> has no attribute 'run_comparison'` (monkeypatch can't patch a name that isn't imported there).

- [ ] **Step 3: Write the implementation**

In `src/intake/pipeline.py`, add the import next to `run_review`:

```python
from src.comparator.service import run_comparison
```

and extend the revision block in `ingest_document` (currently `if result.is_contract_revision:` wrapping `run_review`):

```python
    if result.is_contract_revision:
        try:
            run_review(doc.id, text)
        except Exception:
            logger.exception("review failed for %s; suggestions unavailable", filename)
        try:
            run_comparison(doc.id, text)
        except Exception:
            logger.exception("comparison failed for %s; comparison unavailable", filename)
```

In `src/intake/service.py`, add the same import and extend the revision block in `process_inbox` (currently `if result.is_contract_revision: run_review(doc.id, text)`):

```python
                if result.is_contract_revision:
                    run_review(doc.id, text)
                    try:
                        run_comparison(doc.id, text)
                    except Exception:
                        logger.exception(
                            "comparison failed for %s; comparison unavailable", doc.filename
                        )
```

(Email seam: `run_review` stays unguarded there on purpose — a review failure already fails the whole message for retry, which is existing behavior. Comparison gets its own guard because it must never fail intake. `run_comparison` also catches internally and stores `"failed"`; the seam guards are belt-and-braces.)

In `docs/limitations.md`: change the row
`- [ ] Revision comparison — check the database for similar/prior contracts, compare, and highlight changes (917 request 2026-08-28) — design drafted, not yet built`
to
`- [x] Revision comparison — similar-contract match + LLM compare with validated highlight anchors, "Compared with prior" tab (917 request 2026-08-28) — shipped 2026-09-01`
and add below it:
`- [ ] A failed or no-match comparison has no retry/regenerate path — re-upload to regenerate (same demo-scope shape as failed auto-review).`

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q` → all pass (including the pre-existing intake/api tests, which don't stub `run_comparison` — it must not fire for them because their fakes classify as non-revision, or where they classify as revision the internal try/except in `run_comparison` stores "failed"/"no_match" without network calls **only if an LLM would not be constructed**. Check: `run_comparison` with no candidates returns `no_match` BEFORE any LLM construction, and test DBs start empty, so existing tests that trigger the revision path get `no_match` with no LLM call. If any existing test seeds a second document and hits the LLM path, stub `run_comparison` in that test's monkeypatches the same way `run_review` is stubbed.)

- [ ] **Step 5: Commit**

```bash
git add src/intake/pipeline.py src/intake/service.py docs/limitations.md tests/test_comparator.py
git commit -m "feat: run comparison after review in both intake seams"
```

---

### Task 5: Web API client + types for comparison

**Files (web repo — `/home/penaj/dev/smartwave/contract-review/contract-review-web`):**
- Modify: `src/types/api.ts` (append)
- Modify: `src/lib/api.ts` (append)
- Test: `src/lib/api.test.ts` (append)

**Interfaces:**
- Consumes: the `ComparisonOut` JSON shape from Task 3.
- Produces: `getComparison(documentId: number): Promise<Comparison>`; types `Comparison`, `ComparisonChange` (used by Task 7).

- [ ] **Step 1: Write the failing test**

Append to `src/lib/api.test.ts` (add `getComparison` to the import from `./api`):

```typescript
test('getComparison fetches the comparison for a document', async () => {
  mockFetch(200, {
    status: 'ready',
    matched_document: { id: 3, filename: 'msa-2025.pdf', detected_at: '2026-08-01T00:00:00Z' },
    summary: 'Term doubled.',
    changes: [{ kind: 'modified', clause: 'Term', before_text: 'a', after_text: 'b', note: 'n' }],
  });
  const comparison = await getComparison(7);
  expect(comparison.status).toBe('ready');
  expect(comparison.changes[0].clause).toBe('Term');
  expect(vi.mocked(fetch).mock.calls[0][0]).toContain('/documents/7/comparison');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test`
Expected: FAIL — `getComparison` is not exported from `./api`.

- [ ] **Step 3: Write the implementation**

Append to `src/types/api.ts`:

```typescript
export type ComparisonChange = {
  kind: 'added' | 'removed' | 'modified';
  clause: string;
  before_text: string | null;
  after_text: string | null;
  note: string;
};

export type Comparison = {
  status: 'pending' | 'ready' | 'no_match' | 'failed';
  matched_document: { id: number; filename: string; detected_at: string } | null;
  summary: string | null;
  changes: ComparisonChange[];
};
```

Append to `src/lib/api.ts` (add `Comparison` to the type import):

```typescript
export function getComparison(documentId: number): Promise<Comparison> {
  return request(`/documents/${documentId}/comparison`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test` → all pass.

- [ ] **Step 5: Commit**

```bash
git add src/types/api.ts src/lib/api.ts src/lib/api.test.ts
git commit -m "feat: comparison type and api client"
```

---

### Task 6: Extract the shared anchor-segmentation helper

**Files (web repo):**
- Create: `src/features/document-viewer/segment.ts`
- Modify: `src/features/document-viewer/document-view.tsx` (use the helper; delete the local `segment`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `segment<T>(text: string, items: T[], anchor: (item: T) => string): Array<string | { item: T }>` — callers sort `items` longest-anchor-first themselves (both callers already do).

This is a pure refactor: the existing document-view tests are the safety net; no new tests.

- [ ] **Step 1: Create the helper**

`src/features/document-viewer/segment.ts`:

```typescript
export type Segment<T> = string | { item: T };

/** Split text on each item's anchor. Pass items sorted longest-anchor-first
 *  so a shorter anchor can't split inside a longer one. */
export function segment<T>(
  text: string,
  items: T[],
  anchor: (item: T) => string,
): Segment<T>[] {
  let segments: Segment<T>[] = [text];
  for (const item of items) {
    const needle = anchor(item);
    segments = segments.flatMap((seg) => {
      if (typeof seg !== 'string' || !seg.includes(needle)) return [seg];
      const [before, ...rest] = seg.split(needle);
      return [before, { item }, rest.join(needle)];
    });
  }
  return segments;
}
```

- [ ] **Step 2: Rewire document-view.tsx**

Delete the local `Segment` type and `segment` function from `document-view.tsx`, import the helper, and update `redline`:

```typescript
import { segment } from './segment';
```

```typescript
function redline(text: string, pending: Suggestion[]) {
  return segment(text, pending, (s) => s.original_text).map((seg, i) =>
    typeof seg === 'string' ? (
      <span key={i}>{seg}</span>
    ) : (
      <span key={i}>
        <del className="rounded bg-danger/10 px-0.5 text-danger decoration-danger/60">
          {seg.item.original_text}
        </del>{' '}
        <ins className="rounded bg-success/10 px-0.5 text-success decoration-success/60">
          {seg.item.replacement_text}
        </ins>
      </span>
    ),
  );
}
```

- [ ] **Step 3: Run tests to verify nothing broke**

Run: `npm test` → all pass (especially `longer anchor wins when one original_text is a substring of another`). Run `npx eslint src` — no new warnings.

- [ ] **Step 4: Commit**

```bash
git add src/features/document-viewer/segment.ts src/features/document-viewer/document-view.tsx
git commit -m "refactor: extract generic anchor segmentation helper"
```

---

### Task 7: "Compared with prior" tab

**Files (web repo):**
- Create: `src/features/document-viewer/comparison-view.tsx`
- Modify: `src/features/document-viewer/document-view.tsx` (third tab; comparison fetch; right-column swap)
- Test: `src/features/document-viewer/document-view.test.tsx` (append)

**Interfaces:**
- Consumes: `getComparison` + `Comparison`/`ComparisonChange` types (Task 5), `segment` (Task 6), `Badge`/`Card`/`EmptyState` from `@/components/ui`.
- Produces: `<ComparisonText text={string} comparison={Comparison} />` (left slot: header, summary, highlighted document text) and `<ChangeCard change={ComparisonChange} />` (right slot cards), both exported from `comparison-view.tsx`.

Behavior per spec: the comparison is fetched lazily the first time the tab is opened. While on this tab, the right column shows change cards instead of suggestion cards (versions list stays). States: `pending` → "Comparison in progress…", `no_match` → EmptyState "No similar contract found in the database", `failed` → EmptyState "Comparison unavailable for this document", `ready` → header + summary + highlighted text. Highlight anchors are the `after_text` of `added`/`modified` changes (sorted longest-first); `removed` changes appear only as cards.

- [ ] **Step 1: Write the failing tests**

Append to `src/features/document-viewer/document-view.test.tsx`. Add `getComparison: (...a: unknown[]) => api.getComparison(...a),` to the `vi.mock('@/lib/api', ...)` factory and `getComparison: vi.fn()` to the `api` object. Then:

```typescript
const comparison = (over: Partial<import('@/types/api').Comparison> = {}) => ({
  status: 'ready' as const,
  matched_document: { id: 3, filename: 'msa-2025.pdf', detected_at: '2026-08-01T00:00:00Z' },
  summary: 'Liability cap added; term unchanged.',
  changes: [
    {
      kind: 'modified' as const, clause: 'Liability',
      before_text: 'Liability is unlimited.', after_text: 'Liability is unlimited.',
      note: 'Cap introduced.',
    },
  ],
  ...over,
});

test('comparison tab fetches lazily and renders summary, highlight, and change card', async () => {
  api.getDocument.mockResolvedValue(detail());
  api.getComparison.mockResolvedValue(comparison());
  render(<DocumentView documentId={1} />);
  await waitFor(() => screen.getByRole('tab', { name: /compared with prior/i }));
  expect(api.getComparison).not.toHaveBeenCalled(); // lazy
  await userEvent.click(screen.getByRole('tab', { name: /compared with prior/i }));
  await waitFor(() => expect(screen.getByText(/Liability cap added/)).toBeInTheDocument());
  expect(api.getComparison).toHaveBeenCalledWith(1);
  expect(screen.getByText(/msa-2025\.pdf/)).toBeInTheDocument();
  // after_text is highlighted inside the document text as an <ins>
  expect(screen.getByText('Liability is unlimited.', { selector: 'ins' })).toBeInTheDocument();
  // change card in the right column with kind badge and note
  expect(screen.getByText('Cap introduced.')).toBeInTheDocument();
  expect(screen.getByText('modified')).toBeInTheDocument();
  // suggestion cards are swapped out while on this tab
  expect(screen.queryByRole('button', { name: /accept/i })).not.toBeInTheDocument();
});

test('comparison tab shows the no-match empty state', async () => {
  api.getDocument.mockResolvedValue(detail());
  api.getComparison.mockResolvedValue(comparison({
    status: 'no_match', matched_document: null, summary: null, changes: [],
  }));
  render(<DocumentView documentId={1} />);
  await waitFor(() => screen.getByRole('tab', { name: /compared with prior/i }));
  await userEvent.click(screen.getByRole('tab', { name: /compared with prior/i }));
  await waitFor(() =>
    expect(screen.getByText(/no similar contract found/i)).toBeInTheDocument(),
  );
});

test('comparison tab shows the failed empty state', async () => {
  api.getDocument.mockResolvedValue(detail());
  api.getComparison.mockResolvedValue(comparison({
    status: 'failed', matched_document: null, summary: null, changes: [],
  }));
  render(<DocumentView documentId={1} />);
  await waitFor(() => screen.getByRole('tab', { name: /compared with prior/i }));
  await userEvent.click(screen.getByRole('tab', { name: /compared with prior/i }));
  await waitFor(() =>
    expect(screen.getByText(/comparison unavailable/i)).toBeInTheDocument(),
  );
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: the 3 new tests FAIL — no tab named "Compared with prior" exists.

- [ ] **Step 3: Write the implementation**

`src/features/document-viewer/comparison-view.tsx`:

```typescript
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import type { Comparison, ComparisonChange } from '@/types/api';
import { segment } from './segment';

const kindTones = { added: 'success', removed: 'danger', modified: 'warning' } as const;

export function ChangeCard({ change }: { change: ComparisonChange }) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold">{change.clause}</p>
        <Badge tone={kindTones[change.kind]}>{change.kind}</Badge>
      </div>
      {change.before_text && (
        <p className="text-sm text-text-muted line-through">{change.before_text}</p>
      )}
      {change.after_text && <p className="text-sm">{change.after_text}</p>}
      <p className="text-xs text-text-muted">{change.note}</p>
    </Card>
  );
}

export function ComparisonText({ text, comparison }: { text: string; comparison: Comparison | null }) {
  if (!comparison) return <p className="text-sm text-text-muted">Loading comparison…</p>;
  if (comparison.status === 'pending')
    return <p className="text-sm text-text-muted">Comparison in progress…</p>;
  if (comparison.status === 'no_match')
    return (
      <EmptyState
        title="No similar contract found"
        description="No similar contract found in the database to compare against."
      />
    );
  if (comparison.status === 'failed')
    return (
      <EmptyState
        title="Comparison unavailable"
        description="Comparison unavailable for this document."
      />
    );
  const anchored = comparison.changes
    .filter((c) => (c.kind === 'added' || c.kind === 'modified') && c.after_text)
    .sort((a, b) => (b.after_text as string).length - (a.after_text as string).length);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-sm font-semibold">
          Compared with {comparison.matched_document?.filename}
          {comparison.matched_document &&
            ` · ${new Date(comparison.matched_document.detected_at).toLocaleDateString()}`}
        </p>
        {comparison.summary && <p className="mt-1 text-sm text-text-muted">{comparison.summary}</p>}
      </div>
      <Card className="px-8 py-10 font-serif text-[15px] leading-7 sm:px-12">
        {text.split(/\n{2,}/).map((paragraph, i) => (
          <p key={i} className={i > 0 ? 'mt-4' : ''}>
            {segment(paragraph, anchored, (c) => c.after_text as string).map((seg, j) =>
              typeof seg === 'string' ? (
                <span key={j}>{seg}</span>
              ) : (
                <ins
                  key={j}
                  className="rounded bg-success/10 px-0.5 text-success decoration-success/60"
                >
                  {seg.item.after_text}
                </ins>
              ),
            )}
          </p>
        ))}
      </Card>
    </div>
  );
}
```

In `document-view.tsx`:

1. Imports: add `getComparison` to the `@/lib/api` import, `Comparison` to the types import, and `import { ChangeCard, ComparisonText } from './comparison-view';`
2. State: `const [comparisonData, setComparisonData] = useState<Comparison | null>(null);` and widen the tab union: `useState<'review' | 'original' | 'comparison'>('review')`.
3. Lazy fetch — a tab click handler instead of the bare `setTab`:

```typescript
  const openTab = useCallback((key: 'review' | 'original' | 'comparison') => {
    setTab(key);
    if (key === 'comparison' && comparisonData === null) {
      getComparison(documentId)
        .then(setComparisonData)
        .catch(() => setComparisonData({ status: 'failed', matched_document: null, summary: null, changes: [] }));
    }
  }, [comparisonData, documentId]);
```

4. Tab list — extend the tuple array and use `openTab`:

```typescript
        {([['review', 'Review'], ['original', 'Original document'], ['comparison', 'Compared with prior']] as const).map(([key, label]) => (
```

with `onClick={() => openTab(key)}`.

5. Left slot: render `tab === 'comparison' ? <ComparisonText text={detail.text} comparison={comparisonData} /> : ...existing review/original branches...` (turn the existing ternary into three branches).
6. Right column: wrap the suggestions block (`<p ...>Suggested redlines...` through the confirm bar) in `tab !== 'comparison' && (...)`, and add before the Versions heading:

```typescript
          {tab === 'comparison' && comparisonData?.status === 'ready' && (
            <>
              <p className="text-sm font-semibold">Changes vs prior ({comparisonData.changes.length})</p>
              {comparisonData.changes.length === 0 && (
                <p className="text-sm text-text-muted">No verifiable changes to highlight.</p>
              )}
              {comparisonData.changes.map((c, i) => (
                <ChangeCard key={i} change={c} />
              ))}
            </>
          )}
```

(Check `src/components/ui/empty-state.tsx` for `EmptyState`'s actual props before Step 3 — it is used as `<EmptyState title=... description=... />` elsewhere in the codebase.)

- [ ] **Step 4: Run tests, lint, and build to verify**

Run: `npm test` → all pass (new 3 + all existing, incl. the tab-switching test).
Run: `npx eslint src` → no new warnings. Run: `npm run build` → compiles.

- [ ] **Step 5: Commit**

```bash
git add src/features/document-viewer/comparison-view.tsx src/features/document-viewer/document-view.tsx src/features/document-viewer/document-view.test.tsx
git commit -m "feat: compared-with-prior tab with validated change highlights"
```

---

## Final verification (after all tasks)

- Agent repo: `.venv/bin/python -m pytest tests/ -q` — all pass.
- Web repo: `npm test` and `npm run build` — all pass.
- Both repos: `git log --format='%an <%ae>'` for the new commits shows `ryan-smartwave <ryan@smartwave.ph>`.
- Manual smoke (optional, needs `GOOGLE_API_KEY`/model config): start both apps, upload contract A, then upload a revised contract B → B's viewer shows the "Compared with prior" tab with a match against A.
