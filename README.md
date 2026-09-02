# Contract Review Agent

Python backend for the SmartWave contract-review demo (Globe, presented
Sept 7, 2026). A contract revision arrives — by email, upload, or Google
Drive — and the agent classifies it, reviews it, and compares it against
similar prior contracts, all before a human opens the document. The
Next.js UI lives in the sister repo
[`contract-review-web`](https://github.com/ryan-smartwave/contract-review-web).

## What it does (as of 2026-09-01)

- **Email intake** — polls a Gmail inbox (30s), saves PDF/DOCX attachments,
  ignores everything else. Failed messages roll back and retry.
- **Classification** — LLM decides contract-revision-or-not from the
  document *content* (plus email subject/body), with confidence and
  reasoning persisted.
- **Manual upload & Drive search** — `POST /upload` feeds the same
  pipeline; the `locator` module searches the authorized Google Drive,
  asks a clarifying question on ambiguous matches, and ingests on
  explicit user confirmation.
- **Automatic review** — redline suggestions (clause label, verbatim
  anchor, replacement, rationale) are generated during intake, so they're
  ready before the document is opened. Time-to-ready is measured and
  exposed as `review_seconds`.
- **Batch confirm & save** — the UI stages Accept/Reject decisions and
  posts one `POST /documents/{id}/suggestions/batch`; each confirm
  produces exactly **one** new immutable version plus a labeled DOCX
  (`Contract - v2.docx`). Stale anchors are marked and skipped, never
  applied blindly. (Legacy per-suggestion `/apply` & `/reject` endpoints
  remain.)
- **Revision comparison** — the `comparator` module finds the most
  similar prior contract in the database (LLM match over stored
  documents), LLM-compares the two texts, and keeps only changes whose
  quoted excerpts pass exact-match anchor validation (`count == 1`,
  added-text-absent-from-old, modified-must-differ). Served at
  `GET /documents/{id}/comparison`; rendered as the UI's
  "Compared with prior" tab.

## Architecture

FastAPI app ([`src/main.py`](src/main.py)) with capability modules —
`intake`, `classifier`, `locator`, `reviewer`, `redliner`, `comparator`,
`documents` — each laid out as `router.py` / `schemas.py` / `service.py`
/ `models.py`. Orchestration is plain Python (services call each other
directly); the modules are future A2A sub-agent seams, and an A2A
endpoint + agent card is mounted at `/a2a`. Storage is SQLite via
SQLModel; documents are immutable (new version per confirm). All model
calls go through LangChain's `init_chat_model` (provider set by
`MODEL_NAME`) — never a vendor SDK directly.

## How to run

**1. One-time setup** (Python ≥ 3.12):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install "pytest>=8.3" "httpx>=0.27"   # dev/test deps
```

> Moved or renamed the repo folder? The venv breaks ("bad interpreter") —
> rebuild it: `python3 -m venv --clear .venv` and reinstall as above.

**2. Configure** — create `.env` in the repo root (all settings and their
defaults live in `src/config.py`):

```bash
MODEL_NAME=google_genai:gemini-3.6-flash   # any langchain provider:model
GOOGLE_API_KEY=...                         # or ANTHROPIC_API_KEY for Claude models
ENABLE_GMAIL_POLLER=false
```

SQLite lands in `data/app.db` and stored files in `data/files/` by
default — both created automatically. ⚠ Setting
`ENABLE_GMAIL_POLLER=true` makes the app process the authorized inbox
continuously and **mark matching emails as read**; it also needs
`credentials.json` + `token.json` (see `docs/google-setup.md`;
regenerate the token with `.venv/bin/python -m scripts.google_auth`).
Drive search needs the same Google credentials; upload and review work
without them.

**3. Start the server:**

```bash
.venv/bin/uvicorn src.main:app --reload
```

Serves on http://localhost:8000 — interactive API docs at
http://localhost:8000/docs, agent card at
`/a2a/.well-known/agent-card.json`. Then start the UI from
`contract-review-web` (see its README); it points at
`http://localhost:8000` by default.

**Quick smoke:** upload a PDF/DOCX contract at http://localhost:3000/upload
(or `curl -F "file=@contract.docx" localhost:8000/upload`) and watch the
queue — classification appears in seconds, the redlines chip in ~1–2
minutes.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

106 tests; all LLM calls are faked. The manual end-to-end scripts are
`docs/test-script.md` (local) and `docs/test-script-prod.md` (production).

## Docs

- `docs/superpowers/specs/` — design specs (review engine, revision comparison)
- `docs/superpowers/plans/` — implementation plans
- `docs/limitations.md` — known limitations and accepted demo-scope risks
- `docs/deployment.md` — Railway (this repo) + Vercel (web) deployment
