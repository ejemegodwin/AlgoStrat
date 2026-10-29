# AlgoStrat — Deployment

Status: **not deployed yet.** "Production" today is only the Neon
database. This file is the runbook; it starts with the host decision and
becomes the operating checklist once the first deploy lands.

## Host decision (pending — see comparison below)

Chosen host: **TBD** (record the choice here and as an ADR in
`docs/decisions.md` once made).

Constraints that shape the choice:

- Neon already hosts PostgreSQL — the host only runs the API service
  and the static SPA. No managed DB needed from the host.
- Solo developer, learning-focused: fewer moving parts wins ties.
- GitHub CI already exists; push-to-deploy fits the existing flow.

| | Render (recommended) | Fly.io | Railway |
|---|---|---|---|
| Model | Managed PaaS: web service + static site, one dashboard | Docker-native VMs, manual control | Usage-billed services, smoothest DX |
| Deploys | Push to GitHub | `flyctl` or CI action | Push to GitHub |
| Migrate on deploy | Pre-deploy command or chained start command | `release_command` | Pre-deploy or chained start |
| Cost shape | Free tier (cold starts) or ~$7/mo | ~$3–5/mo, no free tier | Usage-based, less predictable |
| Learning value | Managed-PaaS pattern (transferable) | Docker + ops depth | Lowest, least transferable |

Verify current tier limits and pricing at decision time — they drift.

## Universal checklist (host-independent)

Whatever the host, these are the moving parts:

### API service

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend`
  (no `--reload` in production)
- Migrate on deploy: `alembic upgrade head` as a pre-deploy step, or
  chained: `alembic upgrade head && uvicorn ...` (portable everywhere)
- Health check path: `/health/database`
- Env vars (from `.env.example`): `DATABASE_URL` (prod Neon —
  `ep-cold-sea` endpoint), `JWT_SECRET_KEY`, `JWT_ALGORITHM`,
  `ACCESS_TOKEN_EXPIRE_MINUTES`, `PLATFORM_FEE_PERCENT`,
  `PAYMENT_PROVIDER=simulated`, `CORS_ORIGINS` = the real SPA origin
  (comma-separated allowlist, never `*`)

### SPA (static site)

- Build: `npm install && npm run build` (publish dir: `frontend/dist`)
- Env at build time: `VITE_API_URL` = the deployed API origin
  (see `frontend/.env.example`; `api.js` falls back to localhost without it)
- SPA routing needs a rewrite rule: all paths → `index.html`
- After deploy, set the API's `CORS_ORIGINS` to the SPA's real origin —
  deploy order matters: API first with a temporary allowlist, then the
  SPA, then tighten `CORS_ORIGINS` to the final origin.

### Post-deploy smoke (before announcing it works)

Reuse the preflight pattern from the 2026-10-28 dev-branch smoke:
register → login → post job → apply ×2 → ranked → accept (hire,
auto-close, auto-reject) → milestone loop incl. priced approval with
token and a tok_fail 402 → complete → payout → raise dispute → admin
resolve. Plus CORS preflight from the real SPA origin and a check that
`/health/database` returns ok.

### Secrets hygiene

- Host env var UI is the secret store; nothing secrets-shaped in the
  repo or in `render.yaml`/`fly.toml` (those carry names, not values).
- `JWT_SECRET_KEY` for production is freshly generated, not reused from
  local dev.
