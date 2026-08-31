# Known Limitations & Follow-ups

Status as of 2026-08-28. Friday scope = tracker rows 1–4, 6 (due 2026-08-28).
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
- [x] Backend CORS origins come from the `CORS_ORIGINS` env var (comma-separated;
      defaults to `http://localhost:3000`) — deployed frontends must be listed
      there. *(env-configurable since 2026-08-27)*
- [ ] With the poller enabled and missing/invalid Google credentials, the app
      fails fast at startup (by design; error message is a stack trace). *Phase 2:
      friendlier startup error.*
- [ ] Partial intake rollback can orphan `ClassificationLog` rows (harmless —
      no FK, no crash); an email-path review failure can similarly orphan
      `DocumentVersion` rows. *Phase 2: FK/cascade.*
- [ ] Toolchain pinned: Node 20.15.0 forces Vitest 3/Vite 7 in the web repo.
      *Upgrade Node ≥ 20.19 to unpin.*
- [ ] Review quality is ungrounded — suggestions come from general legal knowledge
      only, with no grounding in a legal-document pool. *Phase 3: add RAG over
      legal-document corpus (source unconfirmed).*

## Known limitations (Phase 2)

- [ ] **Concurrent applies on the same document can lose an update** — single-writer
      demo assumption; no unique constraint on `(document_id, version_number)`.
      *Accepted demo-scope risk 2026-08-27; mitigation known (re-check
      status/version inside the apply transaction).* Batch confirms
      (2026-09-01) share this risk — two concurrent confirms can collide on
      the version number, and now a whole batch (not one apply) can be lost.
      A process crash between the batch's status commit and version creation
      leaves suggestions "applied" with no version (the revert only covers
      in-process exceptions).
- [ ] Batch confirm returns 200 with no explicit `stale_ids` — a skipped
      stale anchor is only visible by diffing suggestion statuses in the
      returned detail (the web UI surfaces a notice this way). *Demo-scope;
      add `stale_ids` to the response if a richer client needs it.*
- [ ] Agent card advertises a relative URL (`/a2a/`) — make it absolute via
      config before any gateway integration (Phase 3).
- [ ] A failed auto-review leaves `review_ready_at` null with no retry
      mechanism or failed-state UI — re-upload/re-confirm to regenerate
      (Phase 3 polish).
- [ ] Generated version files are plain general-format DOCX (no firm-specific
      styling) — per 917 "general use case muna"; customize later.
- [ ] Versions applied before 2026-08-28 (pre-migration rows) have no
      downloadable file — they show as plain text in the version list.

## Deferred by plan (not bugs)

- [x] **Row 5** — clarifying questions on ambiguous search (shipped Phase 2)
- [x] **Row 7** — explicit contract selection/confirmation before review (shipped Phase 2)
- [x] **Rows 8–13** — automatic review, pre-generated redlines + latency metric,
      Apply/Reject UI, versioning + anchor rebasing (shipped Phase 2)
- [x] **Row 14** — output format confirmed by 917 (Eris) 2026-08-28:
      new-version-per-apply plus a labeled new file per applied change
      (e.g. `Contract - v2.docx`), general legal format — shipped 2026-08-28
- [x] A2A endpoint + agent card (shipped Phase 2); gateway deferred until mock exists (per Juls)
- [ ] RAG grounding over legal-document pool — corpus source unconfirmed (Phase 3)
- [ ] Revision comparison — check the database for similar/prior contracts,
      compare, and highlight changes (917 request 2026-08-28) — design drafted,
      not yet built
