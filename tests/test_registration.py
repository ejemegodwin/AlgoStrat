
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import (
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
)
from app.db_session import get_db
from app.main import app
from app.models import Base


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    Base.metadata.create_all(bind=engine)

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
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_password_is_hashed_correctly():
    password = "TestPass123!"

    hashed_password = hash_password(password)

    assert hashed_password != password
    assert verify_password(password, hashed_password) is True
    assert verify_password("WrongPass123!", hashed_password) is False


def test_register_user_successfully(client):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "New Test User",
            "email": "newtest@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 201
    assert response.json()["full_name"] == "New Test User"
    assert response.json()["email"] == "newtest@example.com"
    assert response.json()["account_type"] == "individual"
    assert "password" not in response.json()
    assert "password_hash" not in response.json()


def test_register_user_with_existing_email(client):
    user_data = {
        "full_name": "Duplicate Test User",
        "email": "duplicate@example.com",
        "password": "SecurePass123!",
    }

    first_response = client.post("/auth/register", json=user_data)
    second_response = client.post("/auth/register", json=user_data)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "An account with this email already exists."
    )


def test_register_user_with_short_password(client):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Short Password User",
            "email": "shortpass@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_login_user_successfully(client):
    user_data = {
        "full_name": "Login Test User",
        "email": "login@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )

    login_response = client.post(
        "/auth/login",
        json={
            "email": user_data["email"],
            "password": user_data["password"],
        },
    )

    assert register_response.status_code == 201
    assert login_response.status_code == 200
    assert login_response.json()["access_token"]
    assert login_response.json()["token_type"] == "bearer"

def test_login_user_with_wrong_password(client):
    client.post(
        "/auth/register",
        json={
            "full_name": "Wrong Password User",
            "email": "wrongpass@example.com",
            "password": "SecurePass123!",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "WrongPass123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."

def test_login_user_with_unknown_email(client):
    response = client.post(
        "/auth/login",
        json={
            "email": "unknown@example.com",
            "password": "SecurePass123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."

def test_access_token_returns_correct_user_id():
    token = create_access_token(123)

    user_id = verify_access_token(token)

    assert user_id == 123

def test_invalid_access_token_returns_none():
    user_id = verify_access_token("invalid.token.value")

    assert user_id is None

def test_profile_requires_authentication(client):
    response = client.get("/auth/me")

    assert response.status_code == 401

def test_profile_with_valid_token(client):
    user_data = {
        "full_name": "Token Test User",
        "email": "token-test@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )

    user_id = register_response.json()["id"]
    token = create_access_token(user_id)

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert register_response.status_code == 201
    assert response.status_code == 200
    assert response.json()["id"] == user_id
    assert response.json()["full_name"] == user_data["full_name"]
    assert response.json()["email"] == user_data["email"]
    assert response.json()["account_type"] == "individual"

def test_profile_with_invalid_token_returns_401(client):
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.value"},
    )

    assert response.status_code == 401

def test_profile_with_nonexistent_user_token_returns_401(client):
    token = create_access_token(999999)

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "User no longer exists."


def test_create_job_successfully(client):
    user_data = {
        "full_name": "Job Test User",
        "email": "jobtest@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)

    response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build a website",
            "description": "Create a professional business website.",
            "budget": "500.00",
            "currency": "usd",
        },
    )

    assert response.status_code == 201
    assert response.json()["customer_id"] == user_id
    assert response.json()["title"] == "Build a website"
    assert response.json()["budget"] == "500.00"
    assert response.json()["currency"] == "USD"
    assert response.json()["status"] == "open"


def test_create_job_requires_authentication(client):
    response = client.post(
        "/jobs",
        json={
            "title": "Build a website",
            "description": "Create a professional business website.",
            "budget": "500.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 401


def test_list_jobs_successfully(client):
    user_data = {
        "full_name": "Job Listing User",
        "email": "joblisting@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)

    client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build a portfolio",
            "description": "Create a professional developer portfolio.",
            "budget": "300.00",
            "currency": "USD",
            "category": "Web Development",
            "location": "Lagos, Nigeria",
        },
    )

    response = client.get("/jobs")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Build a portfolio"
    assert response.json()[0]["category"] == "Web Development"
    assert response.json()[0]["location"] == "Lagos, Nigeria"

def test_get_job_successfully(client):
    user_data = {
        "full_name": "Job Details User",
        "email": "jobdetails@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)

    create_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build an API",
            "description": "Develop a REST API for a business.",
            "budget": "750.00",
            "currency": "USD",
        },
    )
    job_id = create_response.json()["id"]

    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["id"] == job_id
    assert response.json()["title"] == "Build an API"
    assert response.json()["customer_id"] == user_id


def test_get_nonexistent_job_returns_404(client):
    response = client.get("/jobs/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found."

def test_close_own_job_successfully(client):
    user_data = {
        "full_name": "Job Owner User",
        "email": "jobowner@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)

    create_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build an online store",
            "description": "Create an online store for a small business.",
            "budget": "1000.00",
            "currency": "USD",
        },
    )
    job_id = create_response.json()["id"]

    response = client.patch(
        f"/jobs/{job_id}/close",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == job_id
    assert response.json()["status"] == "closed"

def test_user_cannot_close_another_users_job(client):
    owner_data = {
        "full_name": "Original Job Owner",
        "email": "originalowner@example.com",
        "password": "SecurePass123!",
    }

    owner_response = client.post(
        "/auth/register",
        json=owner_data,
    )
    owner_id = owner_response.json()["id"]
    owner_token = create_access_token(owner_id)

    create_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a mobile application",
            "description": "Create a mobile application for customers.",
            "budget": "1500.00",
            "currency": "USD",
        },
    )
    job_id = create_response.json()["id"]

    other_user_data = {
        "full_name": "Another User",
        "email": "anotheruser@example.com",
        "password": "SecurePass123!",
    }

    other_user_response = client.post(
        "/auth/register",
        json=other_user_data,
    )
    other_user_id = other_user_response.json()["id"]
    other_user_token = create_access_token(other_user_id)

    response = client.patch(
        f"/jobs/{job_id}/close",
        headers={"Authorization": f"Bearer {other_user_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "You can only close your own jobs."


def test_close_job_requires_authentication(client):
    response = client.patch("/jobs/1/close")

    assert response.status_code == 401

def test_update_own_job_successfully(client):
    user_data = {
        "full_name": "Job Editor",
        "email": "jobeditor@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)

    create_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build an online store",
            "description": "Create an online store for a small business.",
            "budget": "1000.00",
            "currency": "USD",
        },
    )
    job_id = create_response.json()["id"]

    response = client.patch(
        f"/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"budget": "2000.00"},
    )

    assert response.status_code == 200
    assert response.json()["budget"] == "2000.00"
    assert response.json()["title"] == "Build an online store"

def test_user_cannot_update_another_users_job(client):
    owner_data = {
        "full_name": "Original Job Owner",
        "email": "editowner@example.com",
        "password": "SecurePass123!",
    }

    owner_response = client.post(
        "/auth/register",
        json=owner_data,
    )
    owner_id = owner_response.json()["id"]
    owner_token = create_access_token(owner_id)

    create_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a website",
            "description": "Create a website for a small business.",
            "budget": "1000.00",
            "currency": "USD",
        },
    )
    job_id = create_response.json()["id"]

    other_user_data = {
        "full_name": "Another User",
        "email": "editother@example.com",
        "password": "SecurePass123!",
    }

    other_response = client.post(
        "/auth/register",
        json=other_user_data,
    )
    other_id = other_response.json()["id"]
    other_token = create_access_token(other_id)

    response = client.patch(
        f"/jobs/{job_id}",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"budget": "5000.00"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "You can only edit your own jobs."

def test_cannot_update_closed_job(client):
    user_data = {
        "full_name": "Closed Job Owner",
        "email": "closedjobowner@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Build a portfolio website",
            "description": "Create a professional portfolio website.",
            "budget": "1000.00",
            "currency": "USD",
        },
    )
    job_id = create_response.json()["id"]

    close_response = client.patch(
        f"/jobs/{job_id}/close",
        headers=headers,
    )
    assert close_response.status_code == 200

    response = client.patch(
        f"/jobs/{job_id}",
        headers=headers,
        json={"budget": "2000.00"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "You can only edit open jobs."

def test_update_job_rejects_empty_request(client):
    user_data = {
        "full_name": "Empty Update User",
        "email": "emptyupdate@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)

    create_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build a website",
            "description": "Create a website for a small business.",
            "budget": "1000.00",
            "currency": "USD",
        },
    )
    job_id = create_response.json()["id"]

    response = client.patch(
        f"/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Provide at least one field to update."


def test_update_job_rejects_null_title(client):
    user_data = {
        "full_name": "Null Title User",
        "email": "nulltitle@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)

    create_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build a website",
            "description": "Create a website for a small business.",
            "budget": "1000.00",
            "currency": "USD",
        },
    )
    job_id = create_response.json()["id"]

    response = client.patch(
        f"/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": None},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "title cannot be null."


def test_create_job_database_failure_returns_generic_error(client, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    user_data = {
        "full_name": "Database Failure User",
        "email": "dbfailure@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post("/auth/register", json=user_data)
    assert register_response.status_code == 201

    token = create_access_token(register_response.json()["id"])

    def fail_commit(self):
        raise SQLAlchemyError("Sensitive database details")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build a website",
            "description": "Create a professional business website.",
            "budget": "500.00",
            "currency": "USD",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Unable to create job right now. Please try again later."
    )
    assert "Sensitive database details" not in response.text

def test_update_job_database_failure_returns_generic_error(
    client, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    user_data = {
        "full_name": "Update Failure User",
        "email": "updatefailure@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    assert register_response.status_code == 201

    token = create_access_token(register_response.json()["id"])
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Build a website",
            "description": "Create a professional business website.",
            "budget": "500.00",
            "currency": "USD",
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["id"]

    def fail_commit(self):
        raise SQLAlchemyError("Sensitive database details")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = client.patch(
        f"/jobs/{job_id}",
        headers=headers,
        json={"title": "Build a better website"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Unable to update job right now. Please try again later."
    )
    assert "Sensitive database details" not in response.text


def test_close_job_database_failure_returns_generic_error(
    client, monkeypatch
):
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    user_data = {
        "full_name": "Close Failure User",
        "email": "closefailure@example.com",
        "password": "SecurePass123!",
    }

    register_response = client.post(
        "/auth/register",
        json=user_data,
    )
    assert register_response.status_code == 201

    token = create_access_token(register_response.json()["id"])
    headers = {"Authorization": f"Bearer {token}"}

    create_response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Build a website",
            "description": "Create a professional business website.",
            "budget": "500.00",
            "currency": "USD",
        },
    )
    assert create_response.status_code == 201
    job_id = create_response.json()["id"]

    def fail_commit(self):
        raise SQLAlchemyError("Sensitive database details")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = client.patch(
        f"/jobs/{job_id}/close",
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Unable to close job right now. Please try again later."
    )
    assert "Sensitive database details" not in response.text


def test_list_jobs_supports_pagination(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Pagination User",
            "email": "pagination@example.com",
            "password": "SecurePass123!",
        },
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    job_titles = [
        "Build a portfolio",
        "Develop an API",
        "Create a mobile app",
    ]

    created_job_ids = []

    for title in job_titles:
        response = client.post(
            "/jobs",
            headers=headers,
            json={
                "title": title,
                "description": "Complete this professional development project.",
                "budget": "500.00",
                "currency": "USD",
            },
        )
        assert response.status_code == 201
        created_job_ids.append(response.json()["id"])

    response = client.get("/jobs?limit=2&offset=1")

    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 2
    assert [job["id"] for job in jobs] == [
        created_job_ids[1],
        created_job_ids[0],
    ]

def test_list_jobs_rejects_invalid_limit(client):
    response = client.get("/jobs?limit=101")

    assert response.status_code == 422
    assert response.json()["detail"] == "Limit must be between 1 and 100."


def test_list_jobs_rejects_negative_offset(client):
    response = client.get("/jobs?offset=-1")

    assert response.status_code == 422
    assert response.json()["detail"] == "Offset cannot be negative."


def test_list_jobs_filters_by_keyword(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Search User",
            "email": "search@example.com",
            "password": "SecurePass123!",
        },
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    jobs_to_create = [
        {
            "title": "Build a Python API",
            "description": "Create a backend service.",
            "budget": "500.00",
            "currency": "USD",
        },
        {
            "title": "Design a company logo",
            "description": "Create a visual brand identity.",
            "budget": "200.00",
            "currency": "USD",
        },
    ]

    for job_data in jobs_to_create:
        response = client.post(
            "/jobs",
            headers=headers,
            json=job_data,
        )
        assert response.status_code == 201

    response = client.get("/jobs?keyword=python")

    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Build a Python API"


def test_list_jobs_filters_by_currency(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Currency User",
            "email": "currency@example.com",
            "password": "SecurePass123!",
        },
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    jobs_to_create = [
        {
            "title": "Build a Python API",
            "description": "Create a backend service.",
            "budget": "500.00",
            "currency": "USD",
        },
        {
            "title": "Build a business website",
            "description": "Create a website for a business.",
            "budget": "200000.00",
            "currency": "NGN",
        },
    ]

    for job_data in jobs_to_create:
        response = client.post(
            "/jobs",
            headers=headers,
            json=job_data,
        )
        assert response.status_code == 201

    response = client.get("/jobs?currency=ngn")

    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["currency"] == "NGN"


def test_list_jobs_filters_by_budget_range(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Budget User",
            "email": "budget@example.com",
            "password": "SecurePass123!",
        },
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    jobs_to_create = [
        {
            "title": "Build a Python API",
            "description": "Create a backend service.",
            "budget": "500.00",
            "currency": "USD",
        },
        {
            "title": "Design a company logo",
            "description": "Create a visual brand identity.",
            "budget": "200.00",
            "currency": "USD",
        },
        {
            "title": "Build a business website",
            "description": "Create a website for a business.",
            "budget": "1500.00",
            "currency": "USD",
        },
    ]

    for job_data in jobs_to_create:
        response = client.post(
            "/jobs",
            headers=headers,
            json=job_data,
        )
        assert response.status_code == 201

    response = client.get("/jobs?min_budget=300&max_budget=1000")

    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Build a Python API"


def test_list_jobs_rejects_invalid_budget_filters(client):
    invalid_queries = [
        "/jobs?min_budget=-1",
        "/jobs?max_budget=-1",
        "/jobs?min_budget=1000&max_budget=500",
    ]

    for query in invalid_queries:
        response = client.get(query)
        assert response.status_code == 422


def test_list_jobs_filters_by_category(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Category Search User",
            "email": "categorysearch@example.com",
            "password": "SecurePass123!",
        },
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    jobs_to_create = [
        {
            "title": "Build a Python API",
            "description": "Create a backend service.",
            "category": "Web Development",
            "location": "Lagos, Nigeria",
        },
        {
            "title": "Design a company logo",
            "description": "Create a visual brand identity.",
            "category": "Graphic Design",
            "location": "Abuja, Nigeria",
        },
    ]

    for job_data in jobs_to_create:
        response = client.post(
            "/jobs",
            headers=headers,
            json=job_data,
        )
        assert response.status_code == 201

    response = client.get("/jobs?category=web")

    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["category"] == "Web Development"


def test_list_jobs_filters_by_location(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Location Search User",
            "email": "locationsearch@example.com",
            "password": "SecurePass123!",
        },
    )
    user_id = register_response.json()["id"]
    token = create_access_token(user_id)
    headers = {"Authorization": f"Bearer {token}"}

    jobs_to_create = [
        {
            "title": "Build a Python API",
            "description": "Create a backend service.",
            "category": "Web Development",
            "location": "Lagos, Nigeria",
        },
        {
            "title": "Design a company logo",
            "description": "Create a visual brand identity.",
            "category": "Graphic Design",
            "location": "Abuja, Nigeria",
        },
    ]

    for job_data in jobs_to_create:
        response = client.post(
            "/jobs",
            headers=headers,
            json=job_data,
        )
        assert response.status_code == 201

    response = client.get("/jobs?location=lagos")

    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["location"] == "Lagos, Nigeria"


def test_worker_can_apply_for_open_job(client):
    # Register the job owner.
    owner_data = {
        "full_name": "Job Owner",
        "email": "jobowner@example.com",
        "password": "SecurePass123!",
    }
    owner_response = client.post("/auth/register", json=owner_data)
    owner_id = owner_response.json()["id"]
    owner_token = create_access_token(owner_id)

    # The owner creates an open job.
    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a website",
            "description": "Create a professional business website.",
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    # Register a different user who applies for the job.
    worker_data = {
        "full_name": "Job Applicant",
        "email": "applicant@example.com",
        "password": "SecurePass123!",
    }
    worker_response = client.post("/auth/register", json=worker_data)
    worker_id = worker_response.json()["id"]
    worker_token = create_access_token(worker_id)

    response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={
            "cover_letter": (
                "I have experience building professional websites "
                "and can deliver this project successfully."
            ),
        },
    )

    assert response.status_code == 201
    assert response.json()["job_id"] == job_id
    assert response.json()["applicant_id"] == worker_id
    assert response.json()["cover_letter"].startswith("I have experience")
    assert response.json()["status"] == "pending"
    assert response.json()["created_at"]


def test_worker_cannot_apply_for_same_job_twice(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Duplicate Test Owner",
            "email": "duplicate-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Design a logo",
            "description": "Design a unique logo for a new business.",
        },
    )
    job_id = job_response.json()["id"]

    worker_response = client.post(
        "/auth/register",
        json={
            "full_name": "Duplicate Test Worker",
            "email": "duplicate-worker@example.com",
            "password": "SecurePass123!",
        },
    )
    worker_token = create_access_token(worker_response.json()["id"])
    headers = {"Authorization": f"Bearer {worker_token}"}
    application_data = {
        "cover_letter": (
            "I have relevant design experience and would love "
            "to work on this project."
        ),
    }

    first_response = client.post(
        f"/jobs/{job_id}/applications",
        headers=headers,
        json=application_data,
    )
    second_response = client.post(
        f"/jobs/{job_id}/applications",
        headers=headers,
        json=application_data,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "You have already applied for this job."
    )


def test_job_owner_cannot_apply_for_own_job(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Self Apply Owner",
            "email": "self-apply-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_id = owner_response.json()["id"]
    owner_token = create_access_token(owner_id)

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build an API",
            "description": "Build a REST API for a small business.",
        },
    )
    job_id = job_response.json()["id"]

    response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "cover_letter": (
                "I have the skills needed to complete this project."
            ),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "You cannot apply for your own job."
    )


def test_worker_cannot_apply_for_closed_job(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Closed Job Owner",
            "email": "closed-job-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_id = owner_response.json()["id"]
    owner_token = create_access_token(owner_id)

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a Website",
            "description": "Build a professional website for a business.",
        },
    )
    job_id = job_response.json()["id"]

    close_response = client.patch(
        f"/jobs/{job_id}/close",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert close_response.status_code == 200

    worker_response = client.post(
        "/auth/register",
        json={
            "full_name": "Closed Job Worker",
            "email": "closed-job-worker@example.com",
            "password": "SecurePass123!",
        },
    )
    worker_token = create_access_token(worker_response.json()["id"])

    response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={
            "cover_letter": (
                "I have the skills and experience to complete this project."
            ),
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "You can only apply for open jobs."
    )


def test_applying_for_job_requires_authentication(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Authentication Test Owner",
            "email": "application-auth-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Create a Dashboard",
            "description": "Create a dashboard for business reporting.",
        },
    )
    job_id = job_response.json()["id"]

    response = client.post(
        f"/jobs/{job_id}/applications",
        json={
            "cover_letter": (
                "I have the skills and experience to complete this project."
            ),
        },
    )

    assert response.status_code == 401


def test_job_owner_can_view_applications(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Application List Owner",
            "email": "application-list-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_id = owner_response.json()["id"]
    owner_token = create_access_token(owner_id)

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a Reporting Tool",
            "description": "Build a reporting tool for a small business.",
        },
    )
    job_id = job_response.json()["id"]

    worker_response = client.post(
        "/auth/register",
        json={
            "full_name": "Application List Worker",
            "email": "application-list-worker@example.com",
            "password": "SecurePass123!",
        },
    )
    worker_id = worker_response.json()["id"]
    worker_token = create_access_token(worker_id)

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={
            "cover_letter": (
                "I have the skills and experience to build this tool."
            ),
        },
    )
    assert application_response.status_code == 201

    response = client.get(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["job_id"] == job_id
    assert response.json()[0]["applicant_id"] == worker_id
    assert response.json()[0]["status"] == "pending"


def test_user_cannot_view_another_users_job_applications(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Private Applications Owner",
            "email": "private-applications-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a Private Dashboard",
            "description": "Build a dashboard for internal business reports.",
        },
    )
    job_id = job_response.json()["id"]

    other_user_response = client.post(
        "/auth/register",
        json={
            "full_name": "Unauthorized Viewer",
            "email": "unauthorized-viewer@example.com",
            "password": "SecurePass123!",
        },
    )
    other_user_token = create_access_token(
        other_user_response.json()["id"]
    )

    response = client.get(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {other_user_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You can only view applications for your own jobs."
    )


def test_viewing_job_applications_requires_authentication(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Authentication Owner",
            "email": "view-applications-auth-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a Data Dashboard",
            "description": "Build a dashboard for business data analysis.",
        },
    )
    job_id = job_response.json()["id"]

    response = client.get(f"/jobs/{job_id}/applications")

    assert response.status_code == 401


def test_viewing_applications_for_nonexistent_job_returns_404(client):
    user_response = client.post(
        "/auth/register",
        json={
            "full_name": "Missing Job Viewer",
            "email": "missing-job-viewer@example.com",
            "password": "SecurePass123!",
        },
    )
    user_token = create_access_token(user_response.json()["id"])

    response = client.get(
        "/jobs/999999/applications",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found."


def test_job_owner_gets_empty_list_when_no_applications_exist(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "No Applications Owner",
            "email": "no-applications-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Create a Simple Website",
            "description": "Create a simple website for a small business.",
        },
    )
    job_id = job_response.json()["id"]

    response = client.get(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_job_owner_can_accept_application(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Accept Application Owner",
            "email": "accept-application-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_id = owner_response.json()["id"]
    owner_token = create_access_token(owner_id)

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a Reporting Tool",
            "description": "Build a reporting tool for a small business.",
        },
    )
    job_id = job_response.json()["id"]

    worker_response = client.post(
        "/auth/register",
        json={
            "full_name": "Accept Application Worker",
            "email": "accept-application-worker@example.com",
            "password": "SecurePass123!",
        },
    )
    worker_id = worker_response.json()["id"]
    worker_token = create_access_token(worker_id)

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={
            "cover_letter": (
                "I have the skills and experience to build this tool."
            ),
        },
    )
    assert application_response.status_code == 201
    application_id = application_response.json()["id"]

    response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"status": "accepted"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == application_id
    assert response.json()["status"] == "accepted"


def test_job_owner_can_reject_application(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Reject Application Owner",
            "email": "reject-application-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_id = owner_response.json()["id"]
    owner_token = create_access_token(owner_id)

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Create a Business Website",
            "description": "Create a responsive website for a business.",
        },
    )
    job_id = job_response.json()["id"]

    worker_response = client.post(
        "/auth/register",
        json={
            "full_name": "Reject Application Worker",
            "email": "reject-application-worker@example.com",
            "password": "SecurePass123!",
        },
    )
    worker_token = create_access_token(worker_response.json()["id"])

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={
            "cover_letter": (
                "I have the skills and experience to build this website."
            ),
        },
    )
    assert application_response.status_code == 201
    application_id = application_response.json()["id"]

    response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"status": "rejected"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == application_id
    assert response.json()["status"] == "rejected"


def test_non_owner_cannot_update_job_application(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Private Job Owner",
            "email": "private-job-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build an Online Store",
            "description": "Build an online store for a small business.",
        },
    )
    job_id = job_response.json()["id"]

    worker_response = client.post(
        "/auth/register",
        json={
            "full_name": "Private Job Worker",
            "email": "private-job-worker@example.com",
            "password": "SecurePass123!",
        },
    )
    worker_token = create_access_token(worker_response.json()["id"])

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={
            "cover_letter": (
                "I have the skills and experience to build this store."
            ),
        },
    )
    assert application_response.status_code == 201
    application_id = application_response.json()["id"]

    outsider_response = client.post(
        "/auth/register",
        json={
            "full_name": "Unrelated User",
            "email": "unrelated-job-user@example.com",
            "password": "SecurePass123!",
        },
    )
    outsider_token = create_access_token(outsider_response.json()["id"])

    response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={"status": "accepted"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You can only manage applications for your own jobs."
    )

    # Confirm the application was not changed.
    applications_response = client.get(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert applications_response.status_code == 200
    assert applications_response.json()[0]["status"] == "pending"


def test_job_application_rejects_invalid_status(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Invalid Status Owner",
            "email": "invalid-status-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a Mobile App",
            "description": "Build a mobile application for a business.",
        },
    )
    job_id = job_response.json()["id"]

    worker_response = client.post(
        "/auth/register",
        json={
            "full_name": "Invalid Status Worker",
            "email": "invalid-status-worker@example.com",
            "password": "SecurePass123!",
        },
    )
    worker_token = create_access_token(worker_response.json()["id"])

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={
            "cover_letter": (
                "I have the skills and experience to build this application."
            ),
        },
    )
    assert application_response.status_code == 201
    application_id = application_response.json()["id"]

    response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"status": "hired"},
    )

    assert response.status_code == 422


def test_decided_application_cannot_be_updated_again(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Decided Application Owner",
            "email": "decided-application-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Create a Data Dashboard",
            "description": "Create a data dashboard for a small business.",
        },
    )
    job_id = job_response.json()["id"]

    worker_response = client.post(
        "/auth/register",
        json={
            "full_name": "Decided Application Worker",
            "email": "decided-application-worker@example.com",
            "password": "SecurePass123!",
        },
    )
    worker_token = create_access_token(worker_response.json()["id"])

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={
            "cover_letter": (
                "I have the skills and experience to create this dashboard."
            ),
        },
    )
    assert application_response.status_code == 201
    application_id = application_response.json()["id"]

    accepted_response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"status": "accepted"},
    )
    assert accepted_response.status_code == 200
    assert accepted_response.json()["status"] == "accepted"

    rejected_response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"status": "rejected"},
    )

    assert rejected_response.status_code == 400
    assert rejected_response.json()["detail"] == (
        "Only pending applications can be updated."
    )

def test_applicant_can_view_own_applications(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Application Test Owner",
            "email": "my-app-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a mobile app",
            "description": "Build a mobile application for a small business.",
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    applicant_response = client.post(
        "/auth/register",
        json={
            "full_name": "Application Test Applicant",
            "email": "my-applicant@example.com",
            "password": "SecurePass123!",
        },
    )
    applicant_id = applicant_response.json()["id"]
    applicant_token = create_access_token(applicant_id)

    submission_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {applicant_token}"},
        json={
            "cover_letter": (
                "I have the relevant experience and skills "
                "to complete this mobile application project."
            ),
        },
    )
    assert submission_response.status_code == 201

    response = client.get(
        "/applications/me",
        headers={"Authorization": f"Bearer {applicant_token}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["job_id"] == job_id
    assert response.json()[0]["applicant_id"] == applicant_id
    assert response.json()[0]["status"] == "pending"

def test_applicant_cannot_view_another_users_applications(client):
    first_response = client.post(
        "/auth/register",
        json={
            "full_name": "First Applicant",
            "email": "first-applicant@example.com",
            "password": "SecurePass123!",
        },
    )
    first_token = create_access_token(first_response.json()["id"])

    second_response = client.post(
        "/auth/register",
        json={
            "full_name": "Second Applicant",
            "email": "second-applicant@example.com",
            "password": "SecurePass123!",
        },
    )
    second_token = create_access_token(second_response.json()["id"])

    response = client.get(
        "/applications/me",
        headers={"Authorization": f"Bearer {second_token}"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_applicant_with_no_applications_gets_empty_list(client):
    user_response = client.post(
        "/auth/register",
        json={
            "full_name": "No Applications User",
            "email": "no-applications@example.com",
            "password": "SecurePass123!",
        },
    )
    user_token = create_access_token(user_response.json()["id"])

    response = client.get(
        "/applications/me",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 200
    assert response.json() == []

def test_viewing_my_applications_requires_authentication(client):
    response = client.get("/applications/me")

    assert response.status_code == 401

def test_applicant_can_withdraw_own_pending_application(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Withdrawal Owner",
            "email": "withdraw-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build a website",
            "description": "Build a professional website for a business.",
        },
    )
    job_id = job_response.json()["id"]

    applicant_response = client.post(
        "/auth/register",
        json={
            "full_name": "Withdrawal Applicant",
            "email": "withdraw-applicant@example.com",
            "password": "SecurePass123!",
        },
    )
    applicant_token = create_access_token(
        applicant_response.json()["id"]
    )

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {applicant_token}"},
        json={
            "cover_letter": (
                "I have the skills and experience needed for this project."
            ),
        },
    )
    application_id = application_response.json()["id"]

    response = client.patch(
        f"/applications/{application_id}/withdraw",
        headers={"Authorization": f"Bearer {applicant_token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "withdrawn"

    my_applications = client.get(
        "/applications/me",
        headers={"Authorization": f"Bearer {applicant_token}"},
    )
    assert my_applications.status_code == 200
    assert my_applications.json()[0]["status"] == "withdrawn"


def test_applicant_cannot_withdraw_another_users_application(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Protected Job Owner",
            "email": "protected-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Design a logo",
            "description": "Design a logo for a growing business.",
        },
    )
    job_id = job_response.json()["id"]

    applicant_response = client.post(
        "/auth/register",
        json={
            "full_name": "Original Applicant",
            "email": "original-applicant@example.com",
            "password": "SecurePass123!",
        },
    )
    applicant_token = create_access_token(
        applicant_response.json()["id"]
    )

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {applicant_token}"},
        json={
            "cover_letter": (
                "I have relevant experience and can deliver this project."
            ),
        },
    )
    application_id = application_response.json()["id"]

    other_response = client.post(
        "/auth/register",
        json={
            "full_name": "Different Applicant",
            "email": "different-applicant@example.com",
            "password": "SecurePass123!",
        },
    )
    other_token = create_access_token(other_response.json()["id"])

    response = client.patch(
        f"/applications/{application_id}/withdraw",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You can only withdraw your own applications."
    )


def test_applicant_cannot_withdraw_decided_application(client):
    owner_response = client.post(
        "/auth/register",
        json={
            "full_name": "Decision Owner",
            "email": "decision-owner@example.com",
            "password": "SecurePass123!",
        },
    )
    owner_token = create_access_token(owner_response.json()["id"])

    job_response = client.post(
        "/jobs",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "title": "Build an API",
            "description": "Build a secure API for a business.",
        },
    )
    job_id = job_response.json()["id"]

    applicant_response = client.post(
        "/auth/register",
        json={
            "full_name": "Decision Applicant",
            "email": "decision-applicant@example.com",
            "password": "SecurePass123!",
        },
    )
    applicant_token = create_access_token(
        applicant_response.json()["id"]
    )

    application_response = client.post(
        f"/jobs/{job_id}/applications",
        headers={"Authorization": f"Bearer {applicant_token}"},
        json={
            "cover_letter": (
                "I have the backend skills required for this project."
            ),
        },
    )
    application_id = application_response.json()["id"]

    decision_response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"status": "accepted"},
    )
    assert decision_response.status_code == 200

    response = client.patch(
        f"/applications/{application_id}/withdraw",
        headers={"Authorization": f"Bearer {applicant_token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Only pending applications can be withdrawn."
    )
