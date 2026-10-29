# AlgoStrat — Algorithmic Strategies

**An international services marketplace connecting customers with skilled individuals and businesses.**

AlgoStrat makes it easier for people and businesses to find work, hire talent, and manage projects across borders — with verifiable work history, transparent project agreements, milestone-based payments, and explainable matching instead of blind listings. Each account can hire and work; nobody is permanently locked into one side of the marketplace.

## Technology Stack

- **Frontend:** React SPA (Vite, react-router-dom, no state library)
- **Backend:** FastAPI and Python
- **Database:** PostgreSQL (Neon-hosted in production)
- **ORM:** SQLAlchemy
- **Authentication:** JWT access tokens
- **Password security:** Argon2 hashing
- **Database migrations:** Alembic
- **Testing:** pytest and FastAPI TestClient

## Implemented Features

### Authentication and Accounts
- Registration with email validation and case-insensitive email handling
- Argon2 password hashing, JWT login, authenticated profile endpoint
- Uniform login timing for unknown emails and wrong passwords
- Rate limiting on registration and login (in-memory, single-process; shared store needed for multi-instance — see `docs/security.md`)
- Marketplace side chosen at registration: client, worker, or both — enforced by the API and a database constraint (ADR-018)

### Job Management and Discovery
- Create, update, and close your own jobs; closed jobs reject remaining pending applications
- Browse open jobs with pagination, keyword search, and budget/currency/category/location filters
- Currency codes normalized and validated against a curated allowlist

### Applications and Hiring
- Apply with a cover letter; no duplicate or self applications; withdraw while pending
- Accepting an application is an **atomic hire**: the job closes, other pending applications are rejected, and a contract is created — in one transaction, with row locking and a one-accepted-per-job database constraint (ADR-001)

### Contracts and Milestones
- Contract auto-created on hire; client defines milestones with optional prices
- Submit → review loop with revision requests; client-only complete/cancel
- Append-only audit log of every contract event (ADR-008)

### Payments and Payouts
- Double-entry, append-only accrual ledger; derived balances; configurable platform fee (ADR-009)
- Payment provider port with a simulated adapter: clients are charged at priced-milestone approval, declines leave state untouched (ADR-012)
- Workers withdraw cleared balances via payouts
- **Not real money yet** — a live provider (Stripe/Paystack) waits on a registered business; see `docs/roadmap.md`

### Disputes
- Either party can raise a dispute, freezing the contract; one open dispute per contract
- Admin-only resolution with three outcomes (worker favored / client favored / dismissed), including automatic ledger reversals and refunds where money moved (ADR-011)
- Admin queue shows full decision context; consequences spelled out before confirming (ADR-017)

### Matching
- Explainable worker–job matching in both directions: recommended jobs for workers, ranked applicants for job owners
- Four weighted factors, shown to users; newcomers scored neutral, not punished (ADR-010)

### Frontend
- Full SPA flow: register/login → browse/search jobs → apply → ranked applicants → contract milestone loop → payouts → dispute raising and the admin queue
- Role- and status-aware pages; payment tokens on priced approvals; 402s shown as safe retries

### Testing and Quality
- 195+ automated tests: authentication, jobs, applications, contracts, milestones, ledger, payments, payouts, disputes, matching, validation, rate limiting, access control
- SQLite-based unit tests plus PostgreSQL integration tests for locking and concurrency
- GitHub Actions runs migrations and the full suite on PostgreSQL for every push and PR

## API Reference

All protected endpoints require `Authorization: Bearer <access_token>`.
Side-gated endpoints additionally require the matching `account_type`
(client/worker/both — ADR-018). Interactive docs at `/docs` when running.

| Method | Endpoint | Purpose | Authentication |
|---|---|---|---|
| `GET` | `/` | API welcome message | No |
| `GET` | `/health/database` | Database connectivity check | No |
| `POST` | `/auth/register` | Register (email, password, marketplace side) | No |
| `POST` | `/auth/login` | Log in and obtain an access token | No |
| `GET` | `/auth/me` | Authenticated user's profile | Yes |
| `POST` | `/jobs` | Create a job | Client side |
| `GET` | `/jobs` | List/search open jobs | No |
| `GET` | `/jobs/recommended` | Jobs matched to your worker profile | Worker side |
| `GET` | `/jobs/{job_id}` | Job details | No |
| `PATCH` | `/jobs/{job_id}` | Update your own open job | Owner |
| `PATCH` | `/jobs/{job_id}/close` | Close your own job | Owner |
| `POST` | `/jobs/{job_id}/applications` | Apply with a cover letter | Worker side |
| `GET` | `/jobs/{job_id}/applications` | List applications for your job | Owner |
| `GET` | `/jobs/{job_id}/applicants/ranked` | Pending applicants with match factors | Owner |
| `PATCH` | `/jobs/{job_id}/applications/{application_id}` | Accept (hire) or reject | Owner |
| `GET` | `/applications/me` | Your own applications and statuses | Yes |
| `PATCH` | `/applications/{application_id}/withdraw` | Withdraw a pending application | Applicant |
| `GET` | `/profiles/me/worker` | Your worker profile | Yes |
| `PUT` | `/profiles/me/worker` | Create/update worker profile and tags | Worker side |
| `GET` | `/contracts` | Your contracts (either party) | Yes |
| `GET` | `/contracts/{contract_id}` | Contract detail with milestones | Party |
| `GET` | `/contracts/{contract_id}/events` | Audit log | Party |
| `POST` | `/contracts/{contract_id}/milestones` | Add a milestone | Client party |
| `PATCH` | `/milestones/{milestone_id}` | Edit a pending milestone | Client party |
| `DELETE` | `/milestones/{milestone_id}` | Delete a pending milestone | Client party |
| `POST` | `/milestones/{milestone_id}/submit` | Submit work for review | Worker party |
| `POST` | `/milestones/{milestone_id}/review` | Approve (pays if priced) or request changes | Client party |
| `POST` | `/contracts/{contract_id}/complete` | Complete the contract | Client party |
| `POST` | `/contracts/{contract_id}/cancel` | Cancel the contract | Client party |
| `POST` | `/contracts/{contract_id}/disputes` | Raise a dispute (freezes contract) | Party |
| `GET` | `/contracts/{contract_id}/disputes` | Dispute history for a contract | Party |
| `GET` | `/ledger/balance` | Your account balances by currency | Yes |
| `GET` | `/contracts/{contract_id}/ledger` | Ledger entries for a contract | Party |
| `POST` | `/payouts` | Withdraw cleared balance (blank = full) | Yes |
| `GET` | `/payouts` | Your payout history | Yes |
| `GET` | `/admin/disputes` | Open dispute queue with decision context | Admin |
| `POST` | `/admin/disputes/{dispute_id}/resolve` | Resolve a dispute | Admin |

## Documentation

- `docs/architecture.md` — module map and the patterns that protect invariants
- `docs/decisions.md` — every significant decision as an ADR (ADR-001 … ADR-018)
- `docs/security.md` — security posture and the honest list of known limitations
- `docs/roadmap.md` — prioritized backlog and what is blocked on what

## Getting Started

### Prerequisites

- Python 3.12 or a compatible version
- PostgreSQL database (a hosted PostgreSQL service is supported)
- Node.js 20+ (frontend only)
- Git

### 1. Clone the repository

```bash
git clone https://github.com/ejemegodwin/AlgoStrat.git
cd AlgoStrat
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

For development (includes pytest and test tooling):

```bash
pip install -r requirements-dev.txt
```

For production deployments only:

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

`.env.example` documents every variable (`DATABASE_URL`,
`JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`PLATFORM_FEE_PERCENT`, `PAYMENT_PROVIDER`, `CORS_ORIGINS`) without
values. Keep `.env` private — never commit credentials.

### 5. Apply database migrations

```bash
alembic upgrade head
```

### 6. Start the API server

```bash
uvicorn app.main:app --reload --app-dir backend
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to explore the API.

### 7. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies to the local API; `CORS_ORIGINS` defaults to
the Vite dev origin.

### 8. Run the automated tests

```bash
PYTHONPATH=backend python -m pytest -v
```

Most tests run against an isolated in-memory SQLite database. A small
set of PostgreSQL integration tests (concurrency, row locking) is
skipped unless `TEST_DATABASE_URL` points at a dedicated throwaway
PostgreSQL database — never a production or shared one:

```bash
TEST_DATABASE_URL="postgresql://user:password@localhost:5432/algostrat_test" \
    PYTHONPATH=backend python -m pytest -v
```

## Project Status

Backend and frontend are feature-complete through contracts, milestones,
payments (simulated provider), payouts, matching, and disputes with admin
resolution. The next milestone is production deployment; see
`docs/roadmap.md` for the prioritized backlog.

## Vision

Build a dependable, international marketplace where individuals and
businesses can find opportunities, hire talent, and collaborate across
borders — and where a worker's history of completed, verified work
belongs to them, not to any single platform.
