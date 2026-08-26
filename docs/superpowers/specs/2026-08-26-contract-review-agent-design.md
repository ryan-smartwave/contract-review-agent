# Contract Review Agent — Design Spec

**Date:** 2026-08-26
**Owner:** Ryan (SmartWave)
**Client:** Globe — agent demo, presented **September 7, 2026**
**Companion agent:** Collections agent (JC) — out of scope here

## 1. Goal

A contract revision arrives via a monitored Google (Gmail) inbox. The agent
recognizes it as a contract revision, reviews it, and has suggested redlines
ready **before** the human opens the document. The human then applies or
rejects each suggestion with one click.

## 2. Hard constraints (from client meeting)

- **A2A protocol** ([a2aproject/A2A](https://github.com/a2aproject/A2A)): the
  agent must be A2A-aware — it is invoked through an A2A endpoint and
  publishes an agent card.
- **Agent Gateway is Globe's, not ours.** The gateway (token budget, credits,
  routing, model tapping) is client-provided infrastructure. Our boundary is
  the A2A endpoint. **Per Juls (2026-08-26): no gateway work — not even a
  mock — until core functionalities are done. The agent must be buildable and
  demoable standalone.**
- **Orchestrator / multi-agent architecture:** specific capabilities are
  designed as sub-agents. For the demo we build monolith-first with sub-agent
  seams (see §4); a true A2A sub-agent split is a stretch goal.
- **AI abstraction:** no vendor-specific model coupling. Providers
  (Claude/GPT) swappable by configuration.
- **Review is RAG-grounded:** suggestions must be based on hard facts from a
  pool of legal documents, not hallucinated legal opinion. RAG lands in the
  optimization phase, after the workflow works end to end.
- **Out of scope:** Supreme Court decisions (explicitly crossed out by
  client).

## 3. Decisions made

| Decision | Choice | Notes |
|---|---|---|
| Framework | **LangGraph + a2a-sdk (Python)** | Confirmed by Ryan 2026-08-26 (was the open "confirm the framework" item) |
| Gateway in demo | **None for now** | Per Juls; agent stays A2A-compliant so a gateway can front it later unchanged |
| Demo UI | **Custom web app** (Next.js/React + FastAPI) | Doubles as the "SW UI" box on the whiteboard |
| Output format | **New version per applied change** | ⚠ PROPOSAL — must be confirmed with the 917 team (tracker row 14 acceptance criterion). Original never mutated; every Apply produces v1, v2, … with visible history |
| Architecture phasing | **Monolith-first, sub-agent seams** | One LangGraph app, one A2A server; each capability a module with a typed interface = future sub-agent boundary |
| Model access | **LangChain `init_chat_model`** via config/env | Swap `claude-*` / `gpt-*` with zero code changes; no direct Anthropic/OpenAI SDK use |
| Storage | **SQLite + local files** | Demo-scale; documents, versions, suggestions, classification logs, timing metrics |

## 4. Components

**Multi-repo architecture** (decided by Ryan 2026-08-26):

- **`contract-review-agent`** (this repo) — Python backend: LangGraph
  orchestrator + FastAPI server (A2A endpoint + REST). Domain-module layout
  per [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices):
  each capability is a package with its own `router.py`, `schemas.py`,
  `service.py`, `models.py`.
- **`contract-review-web`** (separate repo) — Next.js UI. Feature-based
  layout per [bulletproof-react](https://github.com/alan2207/bulletproof-react)
  (`src/app`, `src/components`, `src/features/*`), with its unidirectional
  import rule: shared → features → app; features never import each other.

Backend repo structure:

```
src/
├── main.py          # FastAPI entrypoint
├── config.py        # settings, model provider selection
├── a2a/             # agent card + A2A server wiring (a2a-sdk)
├── graph/           # LangGraph orchestrator wiring the capability modules
├── intake/          # capability domain modules — each with
├── classifier/      #   router.py, schemas.py, service.py, models.py
├── locator/
├── reviewer/
├── redliner/
├── documents/       # document storage + versioning
└── llm/             # init_chat_model factory (vendor-agnostic)
tests/               # per-module tests, Gmail/Drive fixtures
```

Web repo structure:

```
src/
├── app/             # Next.js app-router pages
├── components/      # shared UI
├── features/
│   ├── review-queue/
│   ├── document-viewer/   # suggestions, Apply/Reject, versions
│   ├── upload/
│   └── drive-search/
├── lib/ config/ hooks/ types/ utils/
```

### Capabilities (LangGraph orchestrator)

Each capability is its own module with a typed interface. These interfaces
are the seams where capabilities later split into real A2A sub-agents.

- **`intake`** — Gmail watcher (API polling) + file-upload handler. Detects
  new emails with attachments in near-real-time; identifies supported types
  (PDF, DOCX); ignores non-document emails without error. Stamps
  `detected_at` for the latency metric.
- **`classifier`** — LLM classification: contract revision vs. not, with
  confidence and reasoning, persisted to a classification log.
- **`locator`** — Google Drive search by user keywords within the authorized
  scope; returns a ranked list (file name, modified date, snippet). Asks a
  clarifying question only when more than one plausible match exists;
  single unambiguous match short-circuits. Zero matches → graceful empty
  state.
- **`reviewer`** — parses the document (PDF/DOCX → text with positional
  info) and generates suggested redlines automatically on
  detection/confirmation — no manual trigger. Each suggestion carries: a
  clause/section anchor, the exact original text span, proposed replacement
  text, and a rationale. Stamps `review_ready_at`; the delta from
  `detected_at` is stored and shown in the UI (row 9 demo metric). Phase 3
  adds RAG retrieval feeding this node's context.
- **`redliner`** — applies an accepted suggestion, producing the next
  document version. **Anchor rebasing:** after each apply, pending
  suggestions' anchors are recomputed against the new version so applying or
  rejecting one suggestion never disturbs the others (rows 11–13). This is
  the trickiest correctness point in the system and gets the densest tests.

### Server (FastAPI, same backend repo)

- A2A endpoint + agent card via `a2a-sdk` (externally-triggered work — what
  Globe's gateway would route).
- Plain REST for the UI's fine-grained interactions: upload, search,
  suggestion list, apply, reject, version history.

### Web UI (Next.js, `contract-review-web` repo)

- **Review queue** — contracts detected from email, with classification and
  the redlines-ready latency stat.
- **Document viewer** — document text with suggestions highlighted at their
  anchored spans; each suggestion card shows Apply/Reject and one of three
  visible states: **pending / applied / rejected** (rejected stays visible,
  marked dismissed — never silently hidden). Suggestions visually distinct
  from original text.
- **Upload screen** — PDF/DOCX upload with received confirmation; feeds the
  same pipeline as email-detected contracts.
- **Drive search screen** — query box, ranked results list, clarifying
  question when ambiguous, explicit selection/confirmation step (selection
  logged and displayed) before review proceeds.
- **Version history** — which edits were applied vs. rejected, per version.

## 5. Data flow

- **Email path (demo headline):** Gmail poll → attachment detected →
  `classifier` → if contract revision, `reviewer` runs immediately →
  suggestions stored → human opens doc in UI with redlines already present.
- **Upload path:** UI upload → same pipeline from `classifier` onward.
- **Drive path:** user query → `locator` → 0/1/many-results handling →
  user confirms selection → `reviewer`.
- **Apply/Reject:** Apply → `redliner` creates new version + rebases pending
  anchors; Reject → suggestion marked dismissed, document untouched. Both
  idempotent (double-click safe).

## 6. Phasing & deadlines

- **Phase 1 — due Friday 2026-08-28** (tracker rows 1–4, 6, all In
  Progress): Gmail monitoring, classification, manual upload, Drive search,
  matching-results display. Includes scaffolding the web app (upload screen,
  results list, detected-contracts list) and **Google Cloud OAuth setup
  first** (Gmail + Drive APIs — the long pole; everything in rows 1, 2, 4
  depends on it).
- **Phase 2 — next week** (rows 5, 7–14): clarifying questions, confirmation
  step, automatic review, pre-generated redlines + latency metric,
  Apply/Reject UI with three suggestion states, versioning + anchor
  rebasing, output format confirmed with 917.
- **Phase 3 — before Sept 7:** RAG grounding over the legal-document pool,
  demo polish; stretch: mock gateway + splitting one capability into a real
  A2A sub-agent.

## 7. Error handling

- Non-document emails: ignored without error.
- Zero Drive matches: explicit "No matching contracts found" state.
- Apply/Reject: idempotent; sequential actions cannot corrupt the document
  (row 13) — guaranteed by immutable versions + anchor rebasing.
- Unsupported file types: rejected at intake with a clear message.

## 8. Testing

TDD per capability module. Gmail/Drive mocked via fixtures:

- `classifier`: known contract-revision emails classified correctly;
  invoices/newsletters classified as not (rows 1–2 acceptance).
- `locator`: ranked results, 0/1/many behavior, clarifying-question gating
  (rows 4–6).
- `reviewer`: suggestion schema completeness (anchor + span + replacement +
  rationale).
- `redliner`: version math, anchor rebasing after apply, independence of
  suggestions, idempotency (rows 11–13).

## 9. Open questions (flagged, not blocking)

1. **Output format** — new-version-per-apply proposed; needs 917 team
   confirmation (row 14). Ask this week; answer needed before `redliner`
   is built.
2. **RAG corpus** — who supplies the legal-document pool (Globe contract
   templates? PH legal references?). Needed before Phase 3.
3. **Gateway mock timing** — revisit with Juls once functionalities are
   done.
