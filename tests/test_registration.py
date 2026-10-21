
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
    assert response.json()["user_id"] == user_id

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