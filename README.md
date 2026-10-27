# AlgoStrat — Algorithmic Strategies

**An international services marketplace connecting customers with skilled individuals and businesses.**

AlgoStrat aims to make it easier for people and businesses to find work opportunities, hire talent, and manage projects across borders. Each account is designed to support both hiring and working, giving users the flexibility to participate on either side of the marketplace.

## Technology Stack

- **Frontend:** React (planned)
- **Backend:** FastAPI and Python
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Authentication:** JWT access tokens
- **Password security:** Secure password hashing
- **Database migrations:** Alembic
- **Testing:** pytest and FastAPI TestClient

## Implemented Features

### Authentication and User Accounts
- User registration with email validation
- Secure password hashing and verification
- User login and JWT access tokens
- Authenticated user profile endpoint
- Authentication protection for private endpoints
- Case-insensitive email handling for registration and login
- Uniform login timing for unknown emails and wrong passwords
- Rate limiting on registration and login (in-memory, single-process; use a shared store such as Redis for multi-instance deployments)

### Job Management
- Create jobs with titles, descriptions, optional budgets, and currencies
- Browse open jobs, with newest jobs listed first
- Retrieve individual job details
- Update your own open jobs
- Close your own jobs
- Validate job updates and reject invalid requests
- Enforce job ownership permissions

### Job Applications
- Submit applications to open jobs
- Include a cover letter with each application
- Prevent duplicate applications to the same job
- Prevent applicants from applying to their own jobs
- Allow job owners to view applications for their jobs
- Allow job owners to accept or reject pending applications
- Accepting an application hires the worker: the job closes automatically and all other pending applications are rejected, atomically
- Each job has at most one accepted application, enforced by a database constraint
- Closing a job rejects its remaining pending applications
- Prevent unauthorized users from managing another owner's applications
- Prevent application decisions from being changed after acceptance or rejection
- Allow applicants to view their own applications and current statuses
- Require authentication to access private application endpoints

### Testing and Quality
- Automated backend tests using pytest
- Tests for authentication, job management, application workflows, validation, and access control
- SQLite-based isolated test database
- PostgreSQL-backed integration tests for concurrency and row-locking behavior
- Continuous integration with GitHub Actions, including migration verification on PostgreSQL
- Database error handling for relevant operations

## API Reference

All protected endpoints require a valid access token in the request header:

`Authorization: Bearer <access_token>`

| Method | Endpoint | Purpose | Authentication |
|---|---|---|---|
| `GET` | `/` | API welcome message | No |
| `GET` | `/health/database` | Check database connectivity | No |
| `POST` | `/auth/register` | Register a user | No |
| `POST` | `/auth/login` | Log in and obtain an access token | No |
| `GET` | `/auth/me` | Retrieve the authenticated user's profile | Yes |
| `POST` | `/jobs` | Create a job | Yes |
| `GET` | `/jobs` | List open jobs | No |
| `GET` | `/jobs/{job_id}` | Retrieve job details | No |
| `PATCH` | `/jobs/{job_id}` | Update your own open job | Yes |
| `PATCH` | `/jobs/{job_id}/close` | Close your own job | Yes |
| `POST` | `/jobs/{job_id}/applications` | Apply for an open job | Yes |
| `GET` | `/jobs/{job_id}/applications` | List applications for your own job | Yes |
| `PATCH` | `/jobs/{job_id}/applications/{application_id}` | Accept or reject a pending application for your job | Yes |
| `GET` | `/applications/me` | List your own applications and their statuses | Yes |
| `PATCH` | `/applications/{application_id}/withdraw` | Withdraw your own pending application | Yes |

Interactive API documentation is available at `/docs` while the API server is running.

## Getting Started

### Prerequisites

- Python 3.12 or a compatible version
- PostgreSQL database (a hosted PostgreSQL service is supported)
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

Create your local environment file:

```bash
cp .env.example .env
```

Edit `.env` and configure:

- `DATABASE_URL` — your PostgreSQL connection string
- `JWT_SECRET_KEY` — a strong, randomly generated secret
- `JWT_ALGORITHM` — the configured JWT signing algorithm
- `ACCESS_TOKEN_EXPIRE_MINUTES` — access-token lifetime in minutes

Keep `.env` private. Never commit database credentials or secret keys to Git.

### 5. Apply database migrations

```bash
alembic upgrade head
```

Ensure your database connection is configured before running migrations.

### 6. Start the API server

```bash
uvicorn app.main:app --reload --app-dir backend
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to explore and test the API.

### 7. Run the automated tests

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

GitHub Actions runs the full suite (including migrations and the
PostgreSQL tests) on every push and pull request.

## Project Status

AlgoStrat is under active development. The backend currently supports authentication, job management, application submission, application review, hiring decisions, and applicant status tracking.

The next development phase will continue strengthening marketplace workflows before expanding the React frontend and preparing for production deployment.

## Roadmap

- [x] Initial project structure
- [x] FastAPI backend
- [x] PostgreSQL connection and database migrations
- [x] User registration and authentication
- [x] Job creation and discovery
- [x] Job detail retrieval
- [x] Job editing and closing with ownership checks
- [x] Job application submission
- [x] Job owners viewing applications
- [x] Accepting and rejecting applications
- [x] Applicants viewing their own application statuses
- [x] Application withdrawal with ownership and status checks
- [ ] React frontend
- [ ] Worker offers and proposals
- [ ] Hiring and contract workflows
- [ ] Payments and platform fees
- [ ] Notifications and messaging
- [ ] Production deployment and monitoring

## Vision

Build a dependable, international marketplace where individuals and businesses can find opportunities, hire talent, and collaborate across borders.
