
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
        },
    )

    response = client.get("/jobs")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Build a portfolio"

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