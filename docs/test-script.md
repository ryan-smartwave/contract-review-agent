# End-to-End Test Script — Phase 1 + 2

Uses the generated kit in `D:\SmartWave\test-documents\`. Each step names the
file to use, the exact action, and the expected result with the tracker row it
proves. Tick as you go.

## 0. Setup (once)

- [ ] Both repos on branch `phase-2` (`git branch --show-current`)
- [ ] Fresh data: stop backend, delete `data\` (skip if already wiped)
- [ ] Backend: `.venv\Scripts\uvicorn src.main:app --port 8000` — starts clean,
      recreates `data\`
- [ ] Web: `npm run dev` → http://localhost:3000 shows an empty review queue
- [ ] `.env` has `ENABLE_GMAIL_POLLER=true` and a working `GOOGLE_API_KEY`
- [ ] ⚠ Quota check: each review costs Gemini calls. If suggestions fail to
      appear later, check the backend log for `429` — free-tier quota resets
      daily (midnight PT)
- [ ] Drive setup (for Part 5): upload **Apex-MSA-Revision-2.pdf**,
      **Meridian-NDA-Amendment-1.docx**, and **contract_revision.pdf** to the
      authorized account's My Drive. Search is name-based, so `revision`
      matches the two files with "revision" in the name (→ clarifying banner)
      while `meridian` matches exactly one (→ no banner)

## 1. Email intake → redlines waiting *(rows 1, 2, 8, 9 — the headline)*

- [ ] 1.1 Email **Apex-MSA-Revision-2.pdf** to the monitored inbox
      (subject: "Revised MSA for your review")
- [ ] 1.2 Within ~30 s the queue shows it, badged **Contract revision** with
      confidence % and reasoning that references the *content* (liability,
      renewal…), not just the filename → **rows 1 + 2**
- [ ] 1.3 Without touching anything, within ~60 s the card gains
      **"redlines ready · Ns"** → **rows 8 + 9** (auto review, measured latency)
- [ ] 1.4 Email a plain message, **no attachment** → nothing appears, no
      backend error → **row 1**
- [ ] 1.5 Email **smartwave-newsletter-august.pdf** ("August newsletter") →
      appears badged **Not a contract revision**, no redlines chip → **row 2**
- [ ] 1.6 The Gmail messages from 1.1/1.5 are now marked read (processed
      signal); the no-attachment mail from 1.4 stays unread

## 2. Manual upload *(row 3 + content-aware hardening)*

- [ ] 2.1 On `/upload`, **drag** `Meridian-NDA-Amendment-1.docx` onto the
      dropzone → filename + size appear inside the box, Upload enables
- [ ] 2.2 Click Upload → green confirmation "Received …" + **Contract
      revision** badge → **row 3**; card appears in the queue and soon gains
      the redlines chip
- [ ] 2.3 Upload **contract_revision.pdf** (the renamed newsletter) →
      **Not a contract revision** — the classifier read the content, not the
      name *(the spoof, closed)*
- [ ] 2.4 Upload **invoice-2026-0847.pdf** → **Not a contract revision**
- [ ] 2.5 Drag **not-a-document.gif** onto the dropzone → inline error
      "Unsupported file type. Upload a PDF or DOCX.", button stays disabled

## 3. Document viewer — Apply / Reject / versions *(rows 10–13)*

Open the **Apex MSA** from the queue (click its filename).

- [ ] 3.1 The **Review** tab shows the contract as a styled document
      (paragraphs, centered title) with each pending suggestion rendered
      inline as a tracked change — red struck-through original, green
      replacement; right panel lists suggestion cards, each with clause label,
      struck-through original, replacement, rationale, and its **own
      Apply/Reject buttons** → **rows 8 + 10**
- [ ] 3.2 Header shows **"redlines ready in Ns"**; the **Original document**
      tab renders the untouched PDF/DOCX with its real styling → **row 9**
- [ ] 3.3 **Apply** the liability-cap suggestion → the inline redline becomes
      plain updated text, card flips to green **applied**, version list gains
      "v2 · from suggestion #N" with a **download link labeled
      "Apex-MSA-Revision-2 - v2.docx"**; other pending cards untouched
      → **rows 11 + 13 + 14**
- [ ] 3.4 **Reject** another suggestion → card marked **rejected**, still
      visible; document text unchanged; **no** new version → **row 12**
- [ ] 3.5 Apply every remaining pending suggestion one by one → each lands,
      one version per apply (v3, v4, … each with its own labeled download),
      no text corruption → **row 13**
- [ ] 3.6 Download **v2** → a valid Word file opens with the applied change
      present; download **v1** → the original file, byte-identical → **row 14**
- [ ] 3.7 Repeat 3.1–3.3 briefly on the **Meridian NDA** (DOCX path)

## 4. Consistency check *(row 14)*

- [ ] 4.1 Across both documents: original file never modified; every Apply =
      a new version **and a new labeled file** (`<name> - v<n>.docx`);
      behavior identical for PDF and DOCX → row 14 (output format
      **confirmed by 917/Eris 2026-08-28**)

## 5. Drive search → clarify → confirm *(rows 4, 5, 6, 7)*

- [ ] 5.1 On `/search`, search **`revision`** (matches Apex-MSA-Revision-2.pdf
      and contract_revision.pdf by name) → ranked results with name + modified
      date + Open-in-Drive link **and** the banner *"I found 2 contracts
      matching 'revision'. Which one should I review?"* → **rows 4 + 6 + 5(ask)**
- [ ] 5.2 Search **`meridian`** (matches one) → single result, **no banner**
      → **row 5 (don't ask when unambiguous)**
- [ ] 5.3 Search **`zzzqq`** → "No matching contracts found" → **row 6**
- [ ] 5.4 From the 5.1 results, click **Review** on the Apex MSA → lands on its
      viewer with classification + suggestions; backend log shows
      "user confirmed drive file …" → **row 7** (selection required + logged;
      your pick after the banner is the row-5 "answer narrows the set" step)

## 6. A2A boundary *(spec, client-facing proof)*

- [ ] 6.1 Open http://localhost:8000/a2a/.well-known/agent-card.json →
      JSON card, `"name": "Contract Review Agent"`, `find_contracts` skill

## 7. Revision comparison — "Compared with prior" tab

- [ ] 7.1 Upload an older MSA (e.g. **Apex-MSA-Revision-1.pdf**, or any
      earlier contract in the kit) **as a contract revision** — this step
      matters: a prior doc classified as *not* a revision never gets a
      `DocumentVersion`, so it stays invisible to comparison matching (see
      `docs/limitations.md`). Let review finish (redlines chip appears).
- [ ] 7.2 Upload a revised version of the *same* contract (e.g.
      **Apex-MSA-Revision-2.pdf**). Let review finish.
- [ ] 7.3 Open the revised document's page → click the **"Compared with
      prior"** tab. Expect: a header naming the matched prior filename, a
      short summary of the differences, the document text with green
      highlighted insertions/modifications, and a right-column list of
      change cards (kind badge, before/after excerpts, one-line note)
- [ ] 7.4 If no prior version exists to match against (or the two documents
      aren't recognized as related), the tab instead shows the **"No similar
      contract found"** empty state — this is expected, not a bug, when
      there's nothing in the database to compare against

## 8. Wrap up

- [ ] 8.1 Flip tracker rows 5, 7–13 to **Done**; row 14 to note "implemented —
      awaiting 917 confirmation"
- [ ] 8.2 Message 917 re: output format
- [ ] 8.3 Choose the merge option (merge ⇒ deploys Railway + Vercel)

**If something fails:** note the step number and what you saw (screenshot or
backend log line) — each step maps to one capability, so the failing module is
immediately identifiable.
