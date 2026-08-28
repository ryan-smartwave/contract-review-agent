# Production Test Script — Railway + Vercel

Same flows as `test-script.md`, run against the deployed stack. Use the same
kit in `D:\SmartWave\test-documents\`. Steps below list what differs from the
local script; where a Part says "as local", follow `test-script.md` verbatim
but on the production URLs.

- **Web:** https://contract-review-web-coral.vercel.app
- **API:** https://contract-review-agent-production.up.railway.app
- **Logs:** Railway dashboard → service → Logs (the deploy log is where
  "user confirmed drive file …" and poller lines appear)

## 0. Pre-flight (once)

- [ ] Latest deploys are live: Railway and Vercel dashboards show the current
      `main` commits (backend `3064107`+, web `ca3b839`+) deployed
- [ ] `GET <API>/documents` returns 200 (JSON list)
- [ ] `GET <API>/a2a/.well-known/agent-card.json` → card with
      `"name": "Contract Review Agent"` and the `find_contracts` skill
- [ ] Web home loads the review queue with no CORS errors in the browser
      console (backend `CORS_ORIGINS` includes the Vercel origin)
- [ ] Site is non-indexable: view-source shows the `noindex` robots meta /
      `<web>/robots.txt` disallows crawling
- [ ] ⚠ Do **not** wipe production data. Documents ingested before
      2026-08-28 render as a single paragraph (pre-paragraph-extraction) and
      their old versions have no download files — expected, not bugs.
      Use fresh uploads for testing.
- [ ] ⚠ Poller: Railway polls the monitored inbox 24/7. If a local backend
      is also running with the poller enabled, whichever polls first ingests
      the email — stop the local one (or expect the email to appear in prod
      only) before Part 1.
- [ ] ⚠ Quota: prod shares the same Gemini key as local. If reviews stop
      appearing, check Railway logs for `429`.

## 1. Email intake → redlines waiting

As local Part 1, but the document appears in the **production** queue.
Confirm the timing story holds over the public internet: badge within ~30 s
of the email, redlines chip within ~90 s, without touching anything.

## 2. Manual upload

As local Part 2, on `<web>/upload`. All five checks apply unchanged
(drag-drop, Meridian revision, renamed-newsletter spoof, invoice, gif
rejection).

## 3. Document viewer — Apply / Reject / versions / downloads

As local Part 3, on a **freshly uploaded** document. Especially:

- [ ] 3.3/3.5 Each Apply adds a version row with a working download link
      (`<name> - v2.docx`, `- v3.docx`, …)
- [ ] 3.6 Downloaded v2 opens in Word with the applied change; downloaded v1
      is the original file byte-for-byte
- [ ] Persistence: refresh the page (and optionally redeploy/restart the
      Railway service) → versions, suggestions, and downloads survive —
      proves the `/data` volume holds both SQLite and generated files

## 4. Consistency check

As local Part 4 — original never modified, new labeled file per apply,
identical for PDF and DOCX (format confirmed by 917/Eris 2026-08-28).

## 5. Drive search → clarify → confirm

As local Part 5 (same Drive account and files; make sure
`contract_revision.pdf` is in that Drive for the 5.1 two-match banner).
The "user confirmed drive file …" line appears in **Railway logs**.

## 6. A2A boundary

- [ ] `GET <API>/a2a/.well-known/agent-card.json` from any machine (no auth)
      → the public agent card, ready to hand to Globe's gateway team

**If something fails here but passes locally**, suspect environment, not
code: Railway env vars (`CORS_ORIGINS`, `GOOGLE_*`, `MODEL_NAME`,
`DATABASE_URL`, `FILES_DIR`), the `/data` volume mount, or Gemini quota —
in that order.
