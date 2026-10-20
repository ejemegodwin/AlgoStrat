
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password, verify_password
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
    assert login_response.json()["message"] == (
        "Credentials verified successfully."
    )
    assert login_response.json()["user_id"] == (
        register_response.json()["id"]
    )

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