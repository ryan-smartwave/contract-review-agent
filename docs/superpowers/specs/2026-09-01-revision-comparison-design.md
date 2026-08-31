# Revision Comparison — Design

**Date:** 2026-09-01
**Status:** Approved approach (pure-LLM comparison), pending spec review
**Origin:** 917 (Eris) request 2026-08-28, re-confirmed 2026-08-31: "when
receiving a file/document: (a) check the database for similar contracts,
(b) compare the documents and highlight changes, (c) update and revise."
Part (c) was clarified to be the batch confirm-and-save flow (shipped
2026-09-01); this spec covers (a) and (b).

## Purpose

When a new contract arrives (email intake, upload, or Drive confirm), the
agent finds the most similar prior contract already in the database,
compares the two, and shows the reviewer what changed — before they open
the document. The existing redline review is unchanged; comparison is a
second, read-only lens.

## Scope

- **In:** similar-contract matching, LLM comparison with validated
  highlight anchors, persistence, REST endpoint, "Compared with prior"
  tab in the web viewer.
- **Out:** RAG grounding over an external legal corpus (separate
  limitations row), feeding the comparison into the reviewer prompt,
  retry/regeneration UI, cross-tenant corpora, embeddings infrastructure.

## Architecture (agent repo — `contract-review-agent`)

New `comparator` capability module under `src/comparator/`, following the
repo convention: `router.py`, `schemas.py`, `service.py`, `models.py`.
Future A2A sub-agent seam, like the other capability modules.

### Data model (`models.py`)

- `Comparison`: `id`, `document_id` (indexed), `matched_document_id`
  (nullable), `status` (`"ready" | "no_match" | "failed"`), `summary`
  (nullable text), `created_at`.
- `ComparisonChange`: `id`, `comparison_id` (indexed), `kind`
  (`"added" | "removed" | "modified"`), `clause` (short human label),
  `before_text` (nullable — verbatim excerpt from the matched prior
  contract), `after_text` (nullable — verbatim excerpt from the new
  document), `note` (one-sentence explanation).

Tables are created by the existing `init_db()` `create_all` path; no
migration needed for new tables.

### Service (`service.py`)

`run_comparison(document_id: int, document_text: str, llm=None) -> Comparison`

1. **Candidate selection.** Fetch all other documents that have at least
   one version; take each one's latest version text. If none exist,
   store `status="no_match"` and return.
2. **Match (LLM call 1).** Prompt with the new document's filename +
   first ~1,500 chars, and each candidate's id, filename + first ~500
   chars. Structured output: `matched_document_id | null` + one-line
   reason. `null` → `status="no_match"`.
3. **Compare (LLM call 2).** Prompt with both full texts (subject to the
   existing `FULL_TEXT_MAX_CHARS` cap). Structured output: `summary`
   (2–4 sentences) and a list of changes, each with `kind`, `clause`,
   `before_text`, `after_text`, `note`. Excerpts must be verbatim,
   within a single paragraph, under 300 chars — same contract as the
   reviewer prompt.
4. **Anchor validation (hallucination guard).** Keep a change only if
   its quoted excerpts pass `text.count(excerpt) == 1`: `after_text`
   against the new document for `added`/`modified`, `before_text`
   against the matched document's latest version text for
   `removed`/`modified`.
   Failing changes are dropped, not shown.
5. Persist `Comparison` + surviving `ComparisonChange` rows,
   `status="ready"`.

Model calls only via the existing `get_chat_model()` /
`init_chat_model` factory — never a vendor SDK directly.

### Trigger

Immediately after `run_review(doc.id, text)` in both seams —
`src/intake/service.py` (email) and `src/intake/pipeline.py`
(upload/Drive) — wrapped best-effort like review: a comparison failure
logs and stores `status="failed"`, never blocks intake. Runs only for
documents classified as contract revisions (same condition as review).

### API (`router.py`)

`GET /documents/{document_id}/comparison` →

```json
{
  "status": "ready",
  "matched_document": {"id": 3, "filename": "MSA 2025.pdf", "detected_at": "..."},
  "summary": "...",
  "changes": [
    {"kind": "modified", "clause": "Section 4 — Liability",
     "before_text": "...", "after_text": "...", "note": "..."}
  ]
}
```

404 if the document doesn't exist; `{"status": "pending"}` shape (200)
if no Comparison row exists yet, so the UI can poll or show a quiet
placeholder. `no_match` and `failed` return their status with empty
changes.

## Web UI (web repo — `contract-review-web`)

New tab **"Compared with prior"** in
`src/features/document-viewer/document-view.tsx`, after "Original
document":

- Header line: matched contract filename + detected date; the LLM
  summary underneath.
- The new document's text rendered as in the review tab, with
  `after_text` anchors highlighted: `added` and `modified` as `ins`-style
  highlights (success tones), reusing the existing longest-anchor-first
  segmentation. `removed` changes have no anchor in the new text and
  appear only as cards.
- A change-card list (clause, kind badge, before/after, note) in the
  right column, mirroring the suggestion-card layout.
- States: `pending` → "Comparison in progress…", `no_match` → empty
  state "No similar contract found in the database", `failed` →
  empty state "Comparison unavailable for this document".
- New API client function `getComparison(documentId)` in `src/lib/api.ts`
  and a `Comparison` type in `src/types/api.ts`.

## Error handling

- Comparison never blocks or fails intake, classification, or review.
- LLM structured-output mismatch or exception → `status="failed"`.
- Anchor validation silently drops non-verifiable changes; if all
  changes are dropped the comparison is still `ready` with the summary
  and zero highlights.
- No retry mechanism (accepted demo-scope, matches failed-review
  behavior; noted in limitations).

## Testing

- **Agent (pytest, fake LLM):** no candidates → `no_match`; match
  returns null → `no_match`; happy path persists summary + changes;
  anchor validation drops fabricated excerpts; LLM exception →
  `failed`; endpoint branches (pending / ready / no_match / 404);
  intake seams still succeed when comparison raises.
- **Web (vitest, mocked API):** tab renders summary, highlights, and
  change cards; longest-anchor precedence; pending / no-match / failed
  empty states.

## Notes

- `docs/limitations.md` revision-comparison row flips to shipped when
  this lands; add a row for "no comparison retry".
- Comparison quality depends on the demo DB actually containing a prior
  similar contract; the demo script should upload the prior version
  first.
