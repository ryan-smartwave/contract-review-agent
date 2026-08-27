# Deployment — Railway (backend) + Vercel (frontend)

Demo-grade deployment. Both platforms deploy straight from the GitHub repos;
sign in to each with GitHub SSO.

## Backend → Railway

1. railway.com → New Project → **Deploy from GitHub repo** →
   `ryan-smartwave/contract-review-agent`. The repo carries `railway.json`
   (start command + healthcheck) and `requirements.txt`; no build config needed.
2. **Attach a volume** (service → right-click → Attach volume), mount path
   `/data`. Without it, the SQLite DB and stored files are wiped on every
   deploy.
3. Service → **Variables** — set:

   | Variable | Value |
   |---|---|
   | `MODEL_NAME` | `google_genai:gemini-3.6-flash` (or any provider:model) |
   | `GOOGLE_API_KEY` | Gemini key (or `ANTHROPIC_API_KEY` for Claude) |
   | `DATABASE_URL` | `sqlite:////data/app.db` (four slashes — absolute path on the volume) |
   | `FILES_DIR` | `/data/files` |
   | `CORS_ORIGINS` | `http://localhost:3000,https://<your-app>.vercel.app` |
   | `ENABLE_GMAIL_POLLER` | `true` (only after the two vars below are set) |
   | `GOOGLE_CREDENTIALS_JSON` | full contents of local `credentials.json` (one line) |
   | `GOOGLE_TOKEN_JSON` | full contents of local `token.json` (one line) |

   The credential files are written to disk at startup when absent
   (`scripts/google_auth.materialize_google_files`); the OAuth browser flow
   never runs headless. Generate/refresh `token.json` locally with
   `.venv\Scripts\python -m scripts.google_auth` and re-paste if it is ever
   revoked.
4. Deploy. Verify `https://<railway-domain>/docs` loads.
5. **Post-deploy check**: verify `/a2a/.well-known/agent-card.json` is
   accessible at `https://<railway-domain>/a2a/.well-known/agent-card.json`.
   This endpoint is required for Globe integration; it is served automatically
   on redeploy.
6. **Note on migrations**: a redeploy after Phase 2 runs an additive SQLite
   migration automatically (`review_ready_at` column added to documents table).
   No manual migration step is required.

⚠ With the poller enabled, the cloud instance processes the authorized inbox
**24/7**, marking unread attachment emails as read. Switch the OAuth token to
a dedicated demo Gmail account before enabling this in the cloud
(see docs/limitations.md).

## Frontend → Vercel

1. vercel.com → Add New Project → import `ryan-smartwave/contract-review-web`.
   Framework auto-detected (Next.js); no build config needed.
2. Environment variable: `NEXT_PUBLIC_API_URL` = `https://<railway-domain>`
   (no trailing slash). It is baked at build time — redeploy after changing it.
3. Deploy, note the `*.vercel.app` domain, and add it to the backend's
   `CORS_ORIGINS` (comma-separated), then redeploy the backend service.

## Local development is unchanged

Defaults (`.env`) keep everything on localhost; none of the variables above
are required locally.
