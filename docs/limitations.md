# Known Limitations & Follow-ups

Status as of 2026-08-27. Friday scope = tracker rows 1–4, 6 (due 2026-08-28).
A checked box means resolved; unchecked means open, with where the fix lands.

## Row 1 — Gmail inbox monitoring (Friday)

- [x] Near-real-time detection works (30s polling; push/webhooks not needed for demo)
- [x] Non-document emails ignored without error
- [x] Failed message processing rolls back cleanly and retries next poll (no duplicates)
- [ ] **Poller runs against ryan@smartwave.ph (real work inbox)** — every unread
      email with a PDF/DOCX attachment gets ingested and **marked as read**.
      Accepted for now (Ryan, 2026-08-27). *Fix: switch to a dedicated demo
      Gmail account before Sept 7 — delete `token.json`, re-run auth.*
- [ ] Same attachment emailed twice creates two documents (no dedupe by
      message/file hash). *Phase 2 if it bothers the demo.*
- [ ] Old-format `.doc` attachments are ignored — only `.pdf`/`.docx` supported
      (per spec). *Confirm with client whether `.doc` matters; else stays.*

## Row 2 — Contract-revision classification (Friday)

- [x] Classifies contract revisions vs. invoices/newsletters on honest traffic
- [x] Decision + confidence + reasoning persisted and shown in UI
- [x] **Classifier now reads document content** — extracts first pages' text
      (pypdf/python-docx) into classification prompt (fixed 2026-08-27, Phase 2)
- [x] Email body now passed in full to classifier (fixed 2026-08-27, Phase 2)

## Row 3 — Manual upload (Friday)

- [x] PDF/DOCX upload through the UI, confirmation + classification shown
- [x] Unsupported types rejected with a clear message
- [x] File picker is an obvious click-to-browse dropzone (fixed 2026-08-27)
- [x] Upload failure rollback implemented (fixed 2026-08-27, Phase 2)
- [x] Drag-and-drop support added to upload dropzone (fixed 2026-08-27, Phase 2)

## Rows 4 + 6 — Drive search & results display (Friday)

- [x] Keyword search within the authorized account's Drive, recency-ranked
- [x] Results show name, modified date, Open-in-Drive link; graceful empty state
- [x] Drive query injection-safe (escaping fixed in review)
- [ ] **Search does not verify results are contracts** — it filters by name
      match + file type (PDF/DOCX/Google Doc) only; `acme-holiday-photos.pdf`
      matches "acme". Within row 4's "likely matching" wording; the human
      confirms (row 6 now, row 7 in Phase 2). *Optional Phase 2: content-aware
      classification pass over top-N results, sharing row 8's text extraction.*
- [ ] No content/full-text search — filename match only. *Phase 2 if needed.*

## Cross-cutting (not tied to a Friday row)

- [ ] Home page has no fetch error boundary — if the backend is down, Next.js
      shows its error page. *Demo ops: start backend first. Phase 2: error state.*
- [ ] Backend CORS is pinned to `http://localhost:3000` — web app must run on
      port 3000 exactly. *Demo ops note.*
- [ ] With the poller enabled and missing/invalid Google credentials, the app
      fails fast at startup (by design; error message is a stack trace). *Phase 2:
      friendlier startup error.*
- [ ] Partial intake rollback can orphan `ClassificationLog` rows (harmless —
      no FK, no crash). *Phase 2: FK/cascade.*
- [ ] Toolchain pinned: Node 20.15.0 forces Vitest 3/Vite 7 in the web repo.
      *Upgrade Node ≥ 20.19 to unpin.*
- [ ] Review quality is ungrounded — suggestions come from general legal knowledge
      only, with no grounding in a legal-document pool. *Phase 3: add RAG over
      legal-document corpus (source unconfirmed).*

## Known limitations (Phase 2)

- [ ] **Concurrent applies on the same document can lose an update** — single-writer
      demo assumption; no unique constraint on `(document_id, version_number)`.
      *Accepted demo-scope risk 2026-08-27; mitigation known (re-check
      status/version inside the apply transaction).*

## Deferred by plan (not bugs)

- [x] **Row 5** — clarifying questions on ambiguous search (shipped Phase 2)
- [x] **Row 7** — explicit contract selection/confirmation before review (shipped Phase 2)
- [x] **Rows 8–13** — automatic review, pre-generated redlines + latency metric,
      Apply/Reject UI, versioning + anchor rebasing (shipped Phase 2)
- [x] **Row 14** — 917 output format: proceeding with new-version-per-apply per
      Ryan 2026-08-27 — confirm before Sept 7
- [x] A2A endpoint + agent card (shipped Phase 2); gateway deferred until mock exists (per Juls)
- [ ] RAG grounding over legal-document pool — corpus source unconfirmed (Phase 3)
