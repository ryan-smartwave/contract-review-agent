# Plan: Downloadable labeled DOCX file per applied version (row 14 follow-up)

**Approved design (chat, 2026-08-28):** 917/Eris confirmed new-version-per-apply
and asked that every applied version also exist as a properly-labeled new file
in a general legal-document format. Original files are never modified.

## Global Constraints

- Principles: DRY, KISS, self-documenting code, YAGNI (CLAUDE.md).
- Model calls only via LangChain `init_chat_model` — this feature makes NO
  model calls; tests must never call live LLM APIs.
- Documents are immutable: the original upload is never modified; every Apply
  creates a new version. This feature adds a generated FILE per applied
  version; v1 (the original snapshot) gets no generated file — it IS the
  original upload.
- Version file label (user-visible filename): `{original stem} - v{n}.docx`,
  e.g. `Apex-MSA-Revision-2 - v2.docx`. On-disk storage: `settings.files_dir /
  f"{uuid4().hex}.docx"` (same convention as originals).
- Generated format is DOCX via python-docx (already a dependency). Plain,
  general-use styling only: ALL-CAPS short paragraphs (the same heuristic the
  web view uses: fewer than 80 chars, contains a letter, equals its uppercase)
  render centered + bold; all other paragraphs are plain. One docx paragraph
  per `\n\n`-separated block.
- Atomicity: the file is written to disk BEFORE the version row commits, so an
  existing version row implies its file exists.
- Backend env: Windows, run tests with `.venv/Scripts/python -m pytest -q`
  from `D:\SmartWave\contract-review-agent`. Full suite currently 65 passed,
  ~5s, fully offline — keep it that way.
- Web env: `D:\SmartWave\contract-review-web`, run `npm test -- --run` and
  `npm run build`. Vitest with explicit imports (`import { expect, test, vi }
  from 'vitest'`).
- Commit per task; end commit messages with
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Task 1 — Backend: render module, version file generation, schema columns

**Repo:** `D:\SmartWave\contract-review-agent` (branch `row-14-version-files`)

TDD: write the tests first, watch them fail, then implement.

1. New test file `tests/test_render.py`:
   - `render_docx` returns bytes that `docx.Document(BytesIO(data))` can open.
   - Given `"MASTER SERVICES AGREEMENT\n\n1. TERM. Twelve months."`, the
     resulting document has 2 paragraphs; the first is centered
     (`WD_ALIGN_PARAGRAPH.CENTER`) with a bold run; the second contains
     "Twelve months" and is not centered.
   - Blank blocks (`"A\n\n\n\nB"`) produce no empty paragraphs.
2. New module `src/documents/render.py`:
   ```python
   from io import BytesIO

   from docx import Document
   from docx.enum.text import WD_ALIGN_PARAGRAPH

   TITLE_MAX_CHARS = 80


   def _is_title(block: str) -> bool:
       return (
           len(block) < TITLE_MAX_CHARS
           and any(c.isalpha() for c in block)
           and block == block.upper()
       )


   def render_docx(text: str) -> bytes:
       doc = Document()
       for block in (b.strip() for b in text.split("\n\n")):
           if not block:
               continue
           paragraph = doc.add_paragraph()
           run = paragraph.add_run(block)
           if _is_title(block):
               paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
               run.bold = True
       buffer = BytesIO()
       doc.save(buffer)
       return buffer.getvalue()
   ```
3. `src/documents/models.py` — `DocumentVersion` gains:
   `file_path: str | None = None` and `filename: str | None = None`.
4. `src/documents/db.py::init_db` — two more idempotent ALTERs, same
   pattern as the existing `review_ready_at` one (each in its own
   try/except OperationalError):
   `ALTER TABLE documentversion ADD COLUMN file_path VARCHAR` and
   `ALTER TABLE documentversion ADD COLUMN filename VARCHAR`.
5. `src/documents/service.py::create_version` — when
   `source_suggestion_id is not None`, inside the existing session: fetch the
   parent `Document`, compute `label = f"{Path(doc.filename).stem} - v{n}.docx"`
   (n = the new version_number), write `render_docx(text_content)` to
   `settings.files_dir / f"{uuid4().hex}.docx"` (mkdir parents first, matching
   `save_document`), and set `file_path`/`filename` on the new version BEFORE
   `session.commit()`. Versions with `source_suggestion_id is None` are
   unchanged (no file).
6. Tests for generation (add to `tests/test_redliner.py` or a focused new
   file): applying a suggestion produces a version whose `filename` is
   `"<stem> - v2.docx"`, whose `file_path` exists on disk, and whose docx
   content (open with python-docx, join paragraph texts) contains the
   suggestion's `replacement_text`. Confirm the original document file bytes
   are untouched. Existing revert-on-failure semantics must keep passing.
7. Run the full suite; commit.

## Task 2 — Backend: version file endpoint + VersionOut.filename

**Repo:** `D:\SmartWave\contract-review-agent` (branch `row-14-version-files`)
Depends on Task 1 (columns + generation exist).

TDD: tests first.

1. `src/documents/router.py` — new endpoint
   `GET /documents/{document_id}/versions/{version_number}/file`:
   - 404 if the document or the version row doesn't exist.
   - If the version has `file_path`: `FileResponse(version.file_path,
     media_type=MIME_TYPES[".docx"], filename=version.filename)`; 404 if the
     file is missing on disk (same guard style as the existing
     `/documents/{id}/file` endpoint).
   - Else if `version_number == 1`: serve the ORIGINAL —
     `FileResponse(doc.file_path, media_type=doc.mime_type,
     filename=doc.filename)`.
   - Else 404 (pre-migration rows without files).
   Fetching the version row needs a small helper in
   `src/documents/service.py` (e.g. `get_version(document_id,
   version_number)`) — keep queries out of the router.
2. `src/documents/schemas.py` — `VersionOut` gains `filename: str | None =
   None`. In `document_detail`, populate it as `v.filename or (doc.filename
   if v.version_number == 1 else None)` so the UI can label v1 with the
   original name without special-casing.
3. Tests in `tests/test_api.py`: v1 serves original bytes/mime/filename;
   an applied version serves DOCX with the label in Content-Disposition;
   unknown version 404s; `GET /documents/{id}` detail shows `filename` on
   both v1 and v2 entries.
4. Run the full suite; commit.

## Task 3 — Web: version download links

**Repo:** `D:\SmartWave\contract-review-web` (branch `row-14-version-files`)
Depends on Task 2 (endpoint + schema shape).

TDD: extend `src/features/document-viewer/document-view.test.tsx` first.

1. `src/types/api.ts` — the version type gains `filename: string | null`.
2. `src/lib/api.ts` — add `versionFileUrl(documentId: number,
   versionNumber: number)` returning
   `` `${BASE}/documents/${documentId}/versions/${versionNumber}/file` ``
   (mirror the existing `documentFileUrl`).
3. `src/features/document-viewer/document-view.tsx` — in the Versions list,
   when `v.filename` is non-null wrap the entry's label in a download link:
   `<a href={versionFileUrl(detail.id, v.version_number)} download
   className="text-primary hover:underline">{v.filename}</a>` alongside the
   existing `v{n} · date · from suggestion #N / original` text. Entries
   without a filename render as today (plain text).
4. Test: a detail with `versions: [{version_number: 1, filename: 'msa.pdf',
   ...}, {version_number: 2, filename: 'msa - v2.docx', ...}]` renders two
   links whose hrefs contain `/versions/1/file` and `/versions/2/file`.
   Update the existing `detail()` fixture to include `filename` so other
   tests keep compiling.
5. Run `npm test -- --run` and `npm run build`; commit.
