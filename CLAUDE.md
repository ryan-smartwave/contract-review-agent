# Contract Review Agent

Agent demo for Globe (presented Sept 7, 2026). A contract revision arrives in a
monitored Gmail inbox; the agent classifies it, reviews it, and has suggested
redlines ready before the human opens the document. Human applies/rejects each
suggestion with one click.

Design spec: `docs/superpowers/specs/2026-08-26-contract-review-agent-design.md`

## Coding principles

- **DRY** — don't repeat yourself. Extract shared logic; one source of truth
  for every rule, schema, and constant.
- **KISS** — keep it simple. Prefer the plainest solution that works; no
  cleverness that needs explaining.
- **Self-documenting code** — names and structure carry the meaning. Comments
  only for constraints the code can't express.
- **YAGNI** — you aren't gonna need it. Build only what the current phase
  requires; no speculative abstractions or config.

## Architecture (short version)

**Multi-repo:** this repo is the Python backend; the Next.js UI lives in a
separate `contract-review-web` repo.

- This repo — LangGraph orchestrator + FastAPI (A2A endpoint + agent card via
  a2a-sdk, REST for the UI). Capabilities (`intake`, `classifier`, `locator`,
  `reviewer`, `redliner`) are domain modules under `src/`, each with its own
  `router.py` / `schemas.py` / `service.py` / `models.py`
  (per zhanymkanov/fastapi-best-practices) — these are the future A2A
  sub-agent seams.
- `contract-review-web` — Next.js UI following bulletproof-react structure
  (`src/app`, `src/components`, `src/features/*`): review queue, document
  viewer with Apply/Reject suggestion cards, upload, Drive search. Import
  rule: shared → features → app; features never import each other.
- Model calls only via LangChain `init_chat_model` (provider from config) —
  never a vendor SDK directly.
- Documents are immutable: every Confirm & save (or legacy single Apply)
  creates a new version — one version per confirmed batch of accepted
  redlines.
- The Agent Gateway is Globe's, not ours; our boundary is the A2A endpoint.
