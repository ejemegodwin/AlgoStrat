from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Contract


def register(client, full_name, email):
    response = client.post(
        "/auth/register",
        json={
            "full_name": full_name,
            "email": email,
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    return user_id, {"Authorization": f"Bearer {create_access_token(user_id)}"}


def create_open_job(client, owner_headers, budget=None, currency=None):
    payload = {
        "title": "Build a company website",
        "description": "Create a professional website for a business.",
    }
    if budget is not None:
        payload["budget"] = budget
    if currency is not None:
        payload["currency"] = currency

    response = client.post("/jobs", headers=owner_headers, json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def apply(client, job_id, worker_headers):
    response = client.post(
        f"/jobs/{job_id}/applications",
        headers=worker_headers,
        json={
            "cover_letter": (
                "I have the skills and experience to complete this project."
            ),
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def decide(client, job_id, application_id, owner_headers, decision):
    return client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers=owner_headers,
        json={"status": decision},
    )


def hire(client, owner_headers, worker_headers, budget=None, currency=None):
    """Run a full hire and return (job_id, application_id)."""
    job_id = create_open_job(client, owner_headers, budget, currency)
    application_id = apply(client, job_id, worker_headers)
    response = decide(
        client, job_id, application_id, owner_headers, "accepted"
    )
    assert response.status_code == 200
    return job_id, application_id


def my_contracts(client, headers):
    response = client.get("/contracts", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_accepting_an_application_creates_a_contract(client):
    owner_id, owner_headers = register(
        client, "Owner", "create-contract-owner@example.com"
    )
    worker_id, worker_headers = register(
        client, "Worker", "create-contract-worker@example.com"
    )
    job_id, application_id = hire(
        client, owner_headers, worker_headers, budget="5000.50", currency="ngn"
    )

    contracts = my_contracts(client, owner_headers)

    assert len(contracts) == 1
    contract = contracts[0]
    assert contract["job_id"] == job_id
    assert contract["application_id"] == application_id
    assert contract["client_id"] == owner_id
    assert contract["worker_id"] == worker_id
    # Terms are a snapshot of the job at hire time (currency normalized).
    assert Decimal(str(contract["agreed_amount"])) == Decimal("5000.50")
    assert contract["currency"] == "NGN"
    assert contract["status"] == "active"
    assert contract["completed_at"] is None


def test_rejecting_an_application_creates_no_contract(client):
    _, owner_headers = register(
        client, "Owner", "reject-contract-owner@example.com"
    )
    _, worker_headers = register(
        client, "Worker", "reject-contract-worker@example.com"
    )
    job_id = create_open_job(client, owner_headers)
    application_id = apply(client, job_id, worker_headers)

    response = decide(
        client, job_id, application_id, owner_headers, "rejected"
    )
    assert response.status_code == 200

    assert my_contracts(client, owner_headers) == []


def test_closing_a_job_creates_no_contract(client):
    _, owner_headers = register(
        client, "Owner", "close-contract-owner@example.com"
    )
    _, worker_headers = register(
        client, "Worker", "close-contract-worker@example.com"
    )
    job_id = create_open_job(client, owner_headers)
    apply(client, job_id, worker_headers)

    response = client.patch(f"/jobs/{job_id}/close", headers=owner_headers)
    assert response.status_code == 200

    assert my_contracts(client, owner_headers) == []


def test_contract_is_listed_for_both_client_and_worker(client):
    _, owner_headers = register(
        client, "Owner", "list-contract-owner@example.com"
    )
    _, worker_headers = register(
        client, "Worker", "list-contract-worker@example.com"
    )
    hire(client, owner_headers, worker_headers)

    owner_contracts = my_contracts(client, owner_headers)
    worker_contracts = my_contracts(client, worker_headers)

    assert len(owner_contracts) == 1
    assert worker_contracts[0]["id"] == owner_contracts[0]["id"]


def test_contract_detail_and_events_are_restricted_to_parties(client):
    _, owner_headers = register(
        client, "Owner", "authz-contract-owner@example.com"
    )
    _, worker_headers = register(
        client, "Worker", "authz-contract-worker@example.com"
    )
    _, outsider_headers = register(
        client, "Outsider", "authz-contract-outsider@example.com"
    )
    hire(client, owner_headers, worker_headers)
    contract_id = my_contracts(client, owner_headers)[0]["id"]

    # Outsiders neither list the contract nor reach it directly.
    assert my_contracts(client, outsider_headers) == []

    detail = client.get(
        f"/contracts/{contract_id}", headers=outsider_headers
    )
    assert detail.status_code == 403

    events = client.get(
        f"/contracts/{contract_id}/events", headers=outsider_headers
    )
    assert events.status_code == 403

    # Both parties can read it.
    for headers in (owner_headers, worker_headers):
        response = client.get(f"/contracts/{contract_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == contract_id


def test_missing_contract_returns_404(client):
    _, owner_headers = register(
        client, "Owner", "missing-contract-owner@example.com"
    )

    response = client.get("/contracts/9999", headers=owner_headers)
    assert response.status_code == 404

    events = client.get("/contracts/9999/events", headers=owner_headers)
    assert events.status_code == 404


def test_contract_requests_require_authentication(client):
    assert client.get("/contracts").status_code == 401
    assert client.get("/contracts/1").status_code == 401
    assert client.get("/contracts/1/events").status_code == 401


def test_contract_created_event_is_recorded(client):
    owner_id, owner_headers = register(
        client, "Owner", "event-contract-owner@example.com"
    )
    _, worker_headers = register(
        client, "Worker", "event-contract-worker@example.com"
    )
    hire(client, owner_headers, worker_headers)
    contract_id = my_contracts(client, owner_headers)[0]["id"]

    response = client.get(
        f"/contracts/{contract_id}/events", headers=owner_headers
    )

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "contract_created"
    assert event["actor_id"] == owner_id
    assert event["milestone_id"] is None
    assert event["contract_id"] == contract_id


def test_contract_detail_includes_an_empty_milestones_list(client):
    _, owner_headers = register(
        client, "Owner", "detail-contract-owner@example.com"
    )
    _, worker_headers = register(
        client, "Worker", "detail-contract-worker@example.com"
    )
    hire(client, owner_headers, worker_headers)
    contract_id = my_contracts(client, owner_headers)[0]["id"]

    response = client.get(f"/contracts/{contract_id}", headers=owner_headers)

    assert response.status_code == 200
    assert response.json()["milestones"] == []


def test_one_contract_per_job_is_enforced_by_the_database(client_and_db):
    client, SessionLocal = client_and_db
    owner_id, owner_headers = register(
        client, "Owner", "unique-contract-owner@example.com"
    )
    worker_id, worker_headers = register(
        client, "Worker", "unique-contract-worker@example.com"
    )
    job_id, application_id = hire(client, owner_headers, worker_headers)

    db = SessionLocal()
    try:
        db.add(
            Contract(
                job_id=job_id,
                application_id=application_id,
                client_id=owner_id,
                worker_id=worker_id,
                currency="USD",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_failed_accept_creates_no_contract(client, monkeypatch):
    _, owner_headers = register(
        client, "Owner", "rollback-contract-owner@example.com"
    )
    _, worker_headers = register(
        client, "Worker", "rollback-contract-worker@example.com"
    )
    job_id = create_open_job(client, owner_headers)
    application_id = apply(client, job_id, worker_headers)

    def fail_commit(self):
        raise SQLAlchemyError("Sensitive database details")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = decide(
        client, job_id, application_id, owner_headers, "accepted"
    )

    assert response.status_code == 503
    assert "Sensitive database details" not in response.text

    monkeypatch.undo()

    # The whole hire rolled back together: no contract, no event.
    assert my_contracts(client, owner_headers) == []
