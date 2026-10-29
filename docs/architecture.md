# AlgoStrat — Architecture

A deliberately boring modular monolith: one FastAPI backend, one React
SPA, one PostgreSQL database (Neon-hosted). No microservices, no message
queues — the architecture is sized for a solo developer who still wants
production discipline. Every significant choice has an ADR in
`docs/decisions.md`; security trade-offs live in `docs/security.md`.
This file is the map.

## Layout

```
backend/
  app/
    main.py            # app factory: CORS middleware, router includes, handlers (~70 lines)
    models.py          # SQLAlchemy models
    schemas.py         # Pydantic v2 request/response schemas
    database.py        # engine/session setup
    db_session.py      # request-scoped session dependency
    core/
      security.py      # JWT, Argon2, require_side (ADR-018), admin check
      rate_limit.py    # in-memory limiter (ADR-004, interim by design)
    routers/           # HTTP layer, one module per domain
      auth.py          # register, login, me
      jobs.py          # CRUD + close + discovery + /jobs/recommended
      applications.py  # apply, list, decide, withdraw, ranked applicants
      contracts.py     # contracts, milestones, events, disputes (party side)
      payouts.py       # worker withdrawals
      profiles.py      # worker profile + tags (matching input)
      ledger.py        # balances, per-contract ledger view
      admin.py         # admin dispute queue + resolution
    services/          # business logic shared across routes
      ledger.py        # double-entry posting, reversals (ADR-009, ADR-011)
      payments.py      # provider port: charge/transfer/refund (ADR-012)
      matching.py      # explainable 4-factor scoring (ADR-010)
  migrations/          # Alembic; never edit an applied migration
frontend/
  src/
    api.js             # the only fetch wrapper
    auth.jsx           # auth context; JWT in localStorage (documented trade-off)
    jobs.js            # shared job-title join helper
    pages/             # one component per route
    components/
tests/                 # pytest; SQLite unit + Postgres integration
```

## Patterns that protect the invariants

These are the load-bearing ideas; changing them without an ADR is a red flag.

- **One transaction per business operation.** Multi-step state changes
  (accept applicant → hire → auto-reject others → close job → create
  contract) commit or roll back together. Accept uses
  `SELECT ... FOR UPDATE` on the job row — Python-level checks alone do
  not prevent races (ADR-001).
- **The database enforces what the code cannot.** Partial unique indexes
  guarantee one accepted application per job and one open dispute per
  contract; CHECK constraints bound statuses and marketplace sides.
- **Append-only records.** `contract_events` and the ledger are never
  updated or deleted. Corrections are reversal entries, not edits
  (mirror-image reversal, idempotency-keyed — ADR-011).
- **Money is Decimal, balances are derived.** No floats anywhere near
  currency; balances are computed from entries, not stored.
- **Payment provider is a port.** `services/payments.py` defines
  `charge`/`transfer`/`refund`; `PAYMENT_PROVIDER=simulated` is the only
  adapter today. A real provider (Stripe/Paystack) drops in behind the
  port without route changes (ADR-012).
- **Matching is explainable.** Four weighted factors (category 0.40,
  budget 0.20, track record 0.25 capped, reliability 0.15), identical
  factors in both directions, newcomers scored neutral rather than
  punished (ADR-010).

## Request flow

```
SPA (api.js) → FastAPI router → authz check (JWT + ownership/side)
  → service (business rules) → SQLAlchemy → PostgreSQL
  → Pydantic response schema → JSON
```

Routers stay thin: authentication, authorization, and shaping. Business
rules live in services or explicitly in the router with a test naming
them. Decimal values serialize as JSON strings — the SPA converts with
`Number()` before arithmetic.

## Frontend

Vite + React (plain JS), `react-router-dom`, no state/data libraries by
choice. JWT lives in localStorage (XSS trade-off accepted, cookie auth is
the documented hardening path — see `docs/security.md`). CORS is an
explicit origin allowlist via `CORS_ORIGINS`, never `*`.

Routes: `/` + `/jobs` (public browse), `/jobs/:jobId` (role-aware:
owner sees ranked applicants, worker sees apply form), `/jobs/new`,
`/applications`, `/contracts`, `/contracts/:contractId` (the milestone
loop + disputes), `/payouts`, `/admin/disputes`, `/login`, `/register`.

## Tests and CI

- Unit tests run on in-memory SQLite for speed.
- PostgreSQL integration tests (locking, partial unique indexes,
  concurrency) run only when `TEST_DATABASE_URL` points at a throwaway
  database — never production; the fixture truncates tables.
- CI (GitHub Actions) spins up postgres:16, applies migrations, runs the
  full suite on every push and PR. No production credentials in CI.

## Configuration

Everything from the environment (see `.env.example`): `DATABASE_URL`,
`JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`PLATFORM_FEE_PERCENT`, `PAYMENT_PROVIDER`, `CORS_ORIGINS`. The app
refuses to start without the required ones. `.env` is git-ignored.
