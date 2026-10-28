from decimal import Decimal

import pytest
from sqlalchemy import func

from app.core.security import create_access_token
from app.models import LedgerAccount, LedgerEntry, LedgerTransaction
from app.services import payments


@pytest.fixture(autouse=True)
def fresh_provider(monkeypatch):
    """The provider singleton caches charges by reference for the whole
    process (that dedup is the point), while milestone ids restart at 1
    in each test's fresh database — so each test gets a clean provider,
    otherwise a decline test could hit a charge cached by an earlier
    test's approval."""
    monkeypatch.setattr(payments, "_provider", None)


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


def hired_contract(client, owner_headers, worker_headers, budget="300.00"):
    job = client.post(
        "/jobs",
        headers=owner_headers,
        json={
            "title": "Build a landing page",
            "description": "Design and implement a marketing landing page.",
            "budget": budget,
            "currency": "USD",
        },
    )
    assert job.status_code == 201
    job_id = job.json()["id"]

    application = client.post(
        f"/jobs/{job_id}/applications",
        headers=worker_headers,
        json={
            "cover_letter": (
                "I have the skills and experience to complete this project."
            ),
        },
    )
    assert application.status_code == 201

    decide = client.patch(
        f"/jobs/{job_id}/applications/{application.json()['id']}",
        headers=owner_headers,
        json={"status": "accepted"},
    )
    assert decide.status_code == 200
    return client.get("/contracts", headers=owner_headers).json()[0]["id"]


def add_priced_milestone(client, contract_id, owner_headers, amount="100.00"):
    response = client.post(
        f"/contracts/{contract_id}/milestones",
        headers=owner_headers,
        json={"title": "First deliverable", "amount": amount},
    )
    assert response.status_code == 201
    return response.json()["id"]


def submit_milestone(client, milestone_id, worker_headers):
    response = client.post(
        f"/milestones/{milestone_id}/submit",
        headers=worker_headers,
        json={"note": "Here is the completed work."},
    )
    assert response.status_code == 200


def approve(client, milestone_id, owner_headers, token="tok_ok"):
    payload = {"decision": "approve"}
    if token is not None:
        payload["payment_token"] = token
    return client.post(
        f"/milestones/{milestone_id}/review",
        headers=owner_headers,
        json=payload,
    )


def earn(client, owner_headers, worker_headers, amount="100.00"):
    """Full cycle: hire, priced milestone, submit, approve (charged)."""
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(
        client, contract_id, owner_headers, amount
    )
    submit_milestone(client, milestone_id, worker_headers)
    assert approve(client, milestone_id, owner_headers).status_code == 200
    return contract_id


def balance_for(client, headers, account_type):
    response = client.get("/ledger/balance", headers=headers)
    assert response.status_code == 200
    for row in response.json():
        if row["account_type"] == account_type:
            return Decimal(str(row["balance"]))
    return Decimal("0")


def platform_cash(db, currency="USD"):
    account = (
        db.query(LedgerAccount)
        .filter_by(
            owner_type="platform",
            account_type="platform_cash",
            currency=currency,
        )
        .one_or_none()
    )
    if account is None:
        return Decimal("0")
    return db.query(
        func.coalesce(func.sum(LedgerEntry.amount), 0)
    ).filter(LedgerEntry.account_id == account.id).scalar()


# --- Charging at approval -------------------------------------------------


def test_priced_approval_requires_a_payment_token(client):
    _, owner_headers = register(client, "Owner", "tok-owner@example.com")
    _, worker_headers = register(client, "Worker", "tok-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)
    submit_milestone(client, milestone_id, worker_headers)

    response = approve(client, milestone_id, owner_headers, token=None)

    assert response.status_code == 400
    detail = client.get(f"/contracts/{contract_id}", headers=owner_headers).json()
    assert detail["milestones"][0]["status"] == "submitted"


def test_declined_charge_posts_nothing_and_can_be_retried(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "dc-owner@example.com")
    _, worker_headers = register(client, "Worker", "dc-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)
    submit_milestone(client, milestone_id, worker_headers)

    declined = approve(client, milestone_id, owner_headers, token="tok_fail")

    assert declined.status_code == 402
    db = SessionLocal()
    try:
        # A declined charge posts NOTHING: the milestone stays submitted
        # and no ledger rows exist (ADR-012).
        assert db.query(LedgerTransaction).count() == 0
    finally:
        db.close()
    detail = client.get(f"/contracts/{contract_id}", headers=owner_headers).json()
    assert detail["milestones"][0]["status"] == "submitted"

    # A retry with a working method succeeds — exactly one charge.
    assert approve(client, milestone_id, owner_headers).status_code == 200
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("100")


def test_successful_approval_posts_accrual_and_settlement(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "ok-owner@example.com")
    _, worker_headers = register(client, "Worker", "ok-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)
    submit_milestone(client, milestone_id, worker_headers)

    assert approve(client, milestone_id, owner_headers).status_code == 200

    # The payable clears in the same transaction that earns the
    # worker's receivable: cash-backed by definition (ADR-012).
    assert balance_for(client, owner_headers, "client_payable") == Decimal("0")
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("100")

    db = SessionLocal()
    try:
        transactions = db.query(LedgerTransaction).all()
        assert sorted(t.type for t in transactions) == ["accrual", "settlement"]
        settlement = next(t for t in transactions if t.type == "settlement")
        assert settlement.idempotency_key == f"settlement:milestone:{milestone_id}"
        assert (
            settlement.provider_reference
            == f"sim_charge:accrual:milestone:{milestone_id}"
        )
        for txn in transactions:
            assert sum(entry.amount for entry in txn.entries) == Decimal("0")
        assert platform_cash(db) == Decimal("100")
    finally:
        db.close()


def test_unpriced_approval_needs_no_token_and_posts_nothing(client):
    _, owner_headers = register(client, "Owner", "unp-owner@example.com")
    _, worker_headers = register(client, "Worker", "unp-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    response = client.post(
        f"/contracts/{contract_id}/milestones",
        headers=owner_headers,
        json={"title": "Unpriced deliverable"},
    )
    milestone_id = response.json()["id"]
    submit_milestone(client, milestone_id, worker_headers)

    assert approve(client, milestone_id, owner_headers, token=None).status_code == 200
    assert client.get(
        f"/contracts/{contract_id}/ledger", headers=owner_headers
    ).json() == []


# --- Payouts ----------------------------------------------------------------


def test_payout_withdraws_the_full_settled_balance(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "po-owner@example.com")
    _, worker_headers = register(client, "Worker", "po-worker@example.com")
    earn(client, owner_headers, worker_headers)

    response = client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "usd", "destination": "Bank account ending 4242"},
    )

    assert response.status_code == 201
    payout = response.json()
    assert Decimal(str(payout["amount"])) == Decimal("100")
    assert payout["currency"] == "USD"  # normalized (ADR-002)
    assert payout["status"] == "succeeded"
    assert payout["provider_reference"] == f"sim_transfer:payout:{payout['id']}"

    # The receivable cleared and the cash left the platform.
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("0")
    db = SessionLocal()
    try:
        assert platform_cash(db) == Decimal("0")
        settlement = db.query(LedgerTransaction).filter_by(
            idempotency_key=f"payout:{payout['id']}"
        ).one()
        assert settlement.type == "settlement"
        # Payout settlements are user-level, not contract-level.
        assert settlement.contract_id is None
        assert sum(e.amount for e in settlement.entries) == Decimal("0")
    finally:
        db.close()

    history = client.get("/payouts", headers=worker_headers).json()
    assert [row["id"] for row in history] == [payout["id"]]


def test_partial_payout_leaves_the_remainder(client):
    _, owner_headers = register(client, "Owner", "pp-owner@example.com")
    _, worker_headers = register(client, "Worker", "pp-worker@example.com")
    earn(client, owner_headers, worker_headers)

    first = client.post(
        "/payouts",
        headers=worker_headers,
        json={
            "currency": "USD",
            "amount": "40.00",
            "destination": "Bank account ending 4242",
        },
    )
    assert first.status_code == 201
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("60")

    second = client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "USD", "destination": "Bank account ending 4242"},
    )
    assert second.status_code == 201
    assert Decimal(str(second.json()["amount"])) == Decimal("60")
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("0")


def test_payout_validation_and_authentication(client):
    _, owner_headers = register(client, "Owner", "pv-owner@example.com")
    _, worker_headers = register(client, "Worker", "pv-worker@example.com")

    # No earnings yet: nothing to pay out.
    assert client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "USD", "destination": "Bank account ending 4242"},
    ).status_code == 400

    earn(client, owner_headers, worker_headers)

    destination = "Bank account ending 4242"
    # Above the settled balance.
    assert client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "USD", "amount": "150.00", "destination": destination},
    ).status_code == 400
    # Non-positive amounts and invalid inputs are schema-rejected.
    assert client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "USD", "amount": "0", "destination": destination},
    ).status_code == 422
    assert client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "USD", "amount": "-5", "destination": destination},
    ).status_code == 422
    assert client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "XXX", "destination": destination},
    ).status_code == 422
    assert client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "USD", "destination": "ab"},
    ).status_code == 422
    # Authentication.
    assert client.post(
        "/payouts", json={"currency": "USD", "destination": destination}
    ).status_code == 401
    assert client.get("/payouts").status_code == 401


def test_payout_history_is_scoped_to_the_owner(client):
    _, owner_headers = register(client, "Owner", "ph-owner@example.com")
    _, worker_headers = register(client, "Worker", "ph-worker@example.com")
    _, other_headers = register(client, "Other", "ph-other@example.com")
    earn(client, owner_headers, worker_headers)

    assert client.post(
        "/payouts",
        headers=worker_headers,
        json={"currency": "USD", "destination": "Bank account ending 4242"},
    ).status_code == 201

    assert len(client.get("/payouts", headers=worker_headers).json()) == 1
    assert client.get("/payouts", headers=other_headers).json() == []


# --- Provider port ------------------------------------------------------------


def test_simulated_provider_dedupes_by_reference():
    provider = payments.get_provider()
    reference = "test:provider-dedup"
    first = provider.charge(
        amount=Decimal("10"), currency="USD", reference=reference, token="tok_ok"
    )
    second = provider.charge(
        amount=Decimal("10"), currency="USD", reference=reference, token="tok_ok"
    )
    # Same reference in, same charge reference out — a retried API call
    # can never double-charge (ADR-012).
    assert second == first
