"""PostgreSQL-backed integration tests.

These tests verify behavior that SQLite cannot: row-level locking
(SELECT ... FOR UPDATE) under real concurrency, and the database
constraints as enforced by PostgreSQL.

They run only when TEST_DATABASE_URL points at a dedicated, throwaway
PostgreSQL database (CI provides one). They are skipped by default
locally. NEVER point TEST_DATABASE_URL at a production or shared
database: the fixture truncates all tables after each test.
"""

import os
import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.rate_limit import login_rate_limiter, register_rate_limiter
from app.core.security import create_access_token
from app.db_session import get_db
from app.main import app
from app.models import Base

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="PostgreSQL integration tests require TEST_DATABASE_URL.",
)


@pytest.fixture
def pg_client():
    login_rate_limiter.reset()
    register_rate_limiter.reset()

    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    # Tables are expected to exist via Alembic migrations in CI;
    # create_all is a no-op then and a convenience otherwise.
    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()

    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE job_applications, jobs, users "
                "RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()


def register(client, email):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Postgres Test User",
            "email": email,
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def apply(client, job_id, headers):
    response = client.post(
        f"/jobs/{job_id}/applications",
        headers=headers,
        json={
            "cover_letter": (
                "I have the skills and experience to complete this project."
            ),
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_concurrent_accepts_hire_exactly_one_worker(pg_client):
    owner_headers = register(pg_client, "pg-race-owner@example.com")
    worker_headers_1 = register(pg_client, "pg-race-worker-1@example.com")
    worker_headers_2 = register(pg_client, "pg-race-worker-2@example.com")

    job_response = pg_client.post(
        "/jobs",
        headers=owner_headers,
        json={
            "title": "Build a company website",
            "description": "Create a professional website for a business.",
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    first_application_id = apply(pg_client, job_id, worker_headers_1)
    second_application_id = apply(pg_client, job_id, worker_headers_2)

    responses = {}

    def accept(application_id, key):
        responses[key] = pg_client.patch(
            f"/jobs/{job_id}/applications/{application_id}",
            headers=owner_headers,
            json={"status": "accepted"},
        )

    threads = [
        threading.Thread(
            target=accept, args=(first_application_id, "first")
        ),
        threading.Thread(
            target=accept, args=(second_application_id, "second")
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # The row lock serializes the two decisions: exactly one hire.
    status_codes = sorted(r.status_code for r in responses.values())
    assert status_codes == [200, 400]

    applications = pg_client.get(
        f"/jobs/{job_id}/applications",
        headers=owner_headers,
    ).json()
    statuses = sorted(a["status"] for a in applications)
    assert statuses == ["accepted", "rejected"]

    job = pg_client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "closed"
