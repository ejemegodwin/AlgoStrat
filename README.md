# AlgoStrat(Algorithmic Strategies)

**An international services marketplace connecting customers with skilled individuals and businesses.**

AlgoStrat aims to make it easier for people and businesses to find work opportunities, hire talent, and manage real-world projects across borders. Each account is intended to support both hiring and working.

## Technology Stack

- **Frontend:** React
- **Backend:** FastAPI (Python)
- **Database:** PostgreSQL
- **Authentication:** JWT (JSON Web Tokens)
- **Database migrations:** Alembic
- **Testing:** pytest

## Implemented Features

### Authentication and User Accounts
- User registration
- Password hashing and verification
- User login and JWT access tokens
- Authenticated user profile endpoint
- Protection for authenticated routes

### Job Management
- Create jobs with a title, description, optional budget, and currency
- List open jobs, with newest jobs returned first
- Retrieve individual job details
- Close your own jobs
- Update your own open jobs
- Validate job updates and reject empty requests
- Enforce job ownership permissions

### Testing and Quality
- Automated backend tests using pytest
- Tests for authentication, job management, validation, and access control

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/register` | Register a user |
| POST | `/auth/login` | Log in and obtain an access token |
| GET | `/auth/me` | Get the authenticated user's profile |
| POST | `/jobs` | Create a job |
| GET | `/jobs` | List open jobs |
| GET | `/jobs/{job_id}` | Get job details |
| PATCH | `/jobs/{job_id}` | Update your own open job |
| PATCH | `/jobs/{job_id}/close` | Close your own job |

Interactive API documentation is available at `/docs` when the FastAPI server is running.

## Getting Started

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

Install the project's Python dependencies using the repository's dependency file, if available.

### 4. Configure environment variables

Create a `.env` file based on `.env.example` and configure the required database connection and authentication secrets. Never commit real credentials or secret keys.

### 5. Run database migrations

Use the project's configured Alembic setup to apply database migrations.

### 6. Start the backend

```bash
uvicorn app.main:app --reload --app-dir backend
```

Open `http://127.0.0.1:8000/docs` to explore the API.

## Project Status

AlgoStrat is under active development. The current focus is building a reliable backend foundation before expanding into the frontend, worker offers, and other marketplace features.

## Roadmap

- [x] Initial project structure
- [x] FastAPI backend
- [x] PostgreSQL connection and database migrations
- [x] User registration and authentication
- [x] Job creation and discovery
- [x] Job detail retrieval
- [x] Job closing with ownership checks
- [x] Job editing with ownership checks
- [ ] React frontend
- [ ] Worker offers and proposals
- [ ] Hiring and contract workflows
- [ ] Payments and platform fees
- [ ] Notifications and messaging
- [ ] Production deployment and monitoring

## Vision

Build a dependable, international marketplace where individuals and businesses can hire, work, and collaborate across borders.
