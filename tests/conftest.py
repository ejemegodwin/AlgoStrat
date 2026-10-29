import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import (
    login_rate_limiter,
    register_rate_limiter,
    verify_rate_limiter,
)
from app.db_session import get_db
from app.main import app
from app.models import Base

# Receipt signing is required-at-use; tests sign with a test-only key.
# Real environments set their own via the environment (.env.example).
os.environ.setdefault("RECEIPT_SIGNING_KEY", "test-only-signing-key")


@pytest.fixture
def client_and_db():
    # Rate limiters are process-global; reset them so tests are isolated.
    login_rate_limiter.reset()
    register_rate_limiter.reset()
    verify_rate_limiter.reset()

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
        yield test_client, TestingSessionLocal

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(client_and_db):
    return client_and_db[0]
