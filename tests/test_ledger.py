from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import LedgerAccount, LedgerEntry, LedgerTransaction, Milestone, Contract
from app.services import ledger as ledger_service


def register(client, full_name, email):
    response = client.post(
        "/auth/register",
        json={
            "full_name": full_name,
            "email": email,
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    return user_id, {"Authorization": f"Bearer {create_access_token(user_id)}"}


def hire(client, owner_headers, worker_headers, budget=None, currency=None):
    """Run a full hire and return the new contract's id."""
    payload = {
        "title": "Build a company website",
        "description": "Create a professional website for a business.",
    }
    if budget is not None:
        payload["budget"] = budget
    if currency is not None:
        payload["currency"] = currency

    job_response = client.post("/jobs", headers=owner_headers, json=payload)
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    apply_response = client.post(
        f"/jobs/{job_id}/applications",
        headers=worker_headers,
        json={
            "cover_letter": (
                "I have the skills and experience to complete this project."
            ),
        },
    )
    application_id = apply_response.json()["id"]

    decide_response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers=owner_headers,
        json={"status": "accepted"},
    )
    assert decide_response.status_code == 200

    contracts = client.get("/contracts", headers=owner_headers).json()
    return contracts[0]["id"]


def setup_contract(client, email_prefix, budget=None, currency=None):
    owner_id, owner_headers = register(
        client, "Owner", f"{email_prefix}-owner@example.com"
    )
    worker_id, worker_headers = register(
        client, "Worker", f"{email_prefix}-worker@example.com"
    )
    contract_id = hire(client, owner_headers, worker_headers, budget, currency)
    return owner_id, owner_headers, worker_id, worker_headers, contract_id


def add_priced_milestone(client, contract_id, owner_headers, amount, title="Priced milestone"):
    response = client.post(
        f"/contracts/{contract_id}/milestones",
        headers=owner_headers,
        json={"title": title, "amount": amount},
    )
    assert response.status_code == 201
    return response.json()["id"]


def submit_and_approve(client, milestone_id, owner_headers, worker_headers):
    submit = client.post(
        f"/milestones/{milestone_id}/submit",
        headers=worker_headers,
        json={"note": "Here is the completed work."},
    )
    assert submit.status_code == 200
    approve = client.post(
        f"/milestones/{milestone_id}/review",
        headers=owner_headers,
        json={"decision": "approve", "payment_token": "tok_ok"},
    )
    assert approve.status_code == 200


def contract_ledger(client, contract_id, headers):
    response = client.get(f"/contracts/{contract_id}/ledger", headers=headers)
    assert response.status_code == 200
    return response.json()


def balance(client, headers):
    response = client.get("/ledger/balance", headers=headers)
    assert response.status_code == 200
    return response.json()


def entries_by_account_type(db, transaction_id):
    """{account_type: amount} for a transaction, via the account join."""
    rows = (
        db.query(LedgerAccount.account_type, LedgerEntry.amount)
        .join(LedgerAccount, LedgerEntry.account_id == LedgerAccount.id)
        .filter(LedgerEntry.transaction_id == transaction_id)
        .all()
    )
    return {account_type: amount for account_type, amount in rows}


def test_approving_a_priced_milestone_posts_a_balanced_accrual(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "accrual", budget="1000", currency="USD"
    )
    milestone_id = add_priced_milestone(client, contract_id, owner_headers, "100.00")

    submit_and_approve(client, milestone_id, owner_headers, worker_headers)

    transactions = contract_ledger(client, contract_id, owner_headers)
    # Accrual + charge settlement (ADR-012).
    assert len(transactions) == 2
    transaction = next(t for t in transactions if t["type"] == "accrual")
    assert transaction["contract_id"] == contract_id
    assert transaction["milestone_id"] == milestone_id

    db = SessionLocal()
    try:
        entries = entries_by_account_type(db, transaction["id"])
        # Fee defaults to 0: the client owes the full amount, the worker
        # earned the full amount, and the books balance.
        assert entries == {
            "client_payable": Decimal("100.00"),
            "worker_receivable": Decimal("-100.00"),
        }
        assert sum(entries.values()) == 0

        txn = db.query(LedgerTransaction).filter_by(id=transaction["id"]).first()
        assert txn.idempotency_key == f"accrual:milestone:{milestone_id}"
    finally:
        db.close()


def test_approving_an_unpriced_milestone_posts_nothing(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "unpriced"
    )
    response = client.post(
        f"/contracts/{contract_id}/milestones",
        headers=owner_headers,
        json={"title": "Unpriced milestone"},
    )
    milestone_id = response.json()["id"]

    submit_and_approve(client, milestone_id, owner_headers, worker_headers)

    assert contract_ledger(client, contract_id, owner_headers) == []


def test_fee_split_when_configured(client_and_db, monkeypatch):
    client, SessionLocal = client_and_db
    monkeypatch.setattr(ledger_service, "PLATFORM_FEE_PERCENT", Decimal("10"))

    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "fee", budget="1000", currency="USD"
    )
    milestone_id = add_priced_milestone(client, contract_id, owner_headers, "100.00")
    submit_and_approve(client, milestone_id, owner_headers, worker_headers)

    db = SessionLocal()
    try:
        transaction = db.query(LedgerTransaction).filter_by(type="accrual").one()
        entries = entries_by_account_type(db, transaction.id)
        assert entries == {
            "client_payable": Decimal("100.00"),
            "worker_receivable": Decimal("-90.00"),
            "platform_revenue": Decimal("-10.00"),
        }
        assert sum(entries.values()) == 0
    finally:
        db.close()


def test_fee_rounding_keeps_the_books_exactly_balanced(client_and_db, monkeypatch):
    client, SessionLocal = client_and_db
    monkeypatch.setattr(ledger_service, "PLATFORM_FEE_PERCENT", Decimal("10"))

    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "rounding", budget="1000", currency="USD"
    )
    # 19.99 * 10% = 1.999 -> fee rounds to 2.00; the worker gets the rest.
    milestone_id = add_priced_milestone(client, contract_id, owner_headers, "19.99")
    submit_and_approve(client, milestone_id, owner_headers, worker_headers)

    db = SessionLocal()
    try:
        transaction = db.query(LedgerTransaction).filter_by(type="accrual").one()
        entries = entries_by_account_type(db, transaction.id)
        assert entries["platform_revenue"] == Decimal("-2.00")
        assert entries["worker_receivable"] == Decimal("-17.99")
        assert sum(entries.values()) == 0
    finally:
        db.close()


def test_balances_accumulate_across_approvals(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "accumulate", budget="1000", currency="USD"
    )
    first = add_priced_milestone(client, contract_id, owner_headers, "100.00", title="First priced milestone")
    second = add_priced_milestone(client, contract_id, owner_headers, "150.00", title="Second priced milestone")
    submit_and_approve(client, first, owner_headers, worker_headers)
    submit_and_approve(client, second, owner_headers, worker_headers)

    client_balance = balance(client, owner_headers)
    assert len(client_balance) == 1
    assert client_balance[0]["account_type"] == "client_payable"
    # Charged at approval (ADR-012): the payable clears immediately.
    assert Decimal(str(client_balance[0]["balance"])) == Decimal("0")

    worker_balance = balance(client, worker_headers)
    assert len(worker_balance) == 1
    assert worker_balance[0]["account_type"] == "worker_receivable"
    assert Decimal(str(worker_balance[0]["balance"])) == Decimal("250.00")


def test_balances_are_tracked_per_currency(client):
    owner_id, owner_headers = register(client, "Owner", "fx-owner@example.com")
    worker_id, worker_headers = register(client, "Worker", "fx-worker@example.com")

    usd_contract = hire(client, owner_headers, worker_headers, currency="USD")
    ngn_contract = hire(client, owner_headers, worker_headers, currency="NGN")

    usd_milestone = add_priced_milestone(client, usd_contract, owner_headers, "100.00")
    ngn_milestone = add_priced_milestone(client, ngn_contract, owner_headers, "50000.00")
    submit_and_approve(client, usd_milestone, owner_headers, worker_headers)
    submit_and_approve(client, ngn_milestone, owner_headers, worker_headers)

    worker_balance = balance(client, worker_headers)
    by_currency = {row["currency"]: row for row in worker_balance}
    assert set(by_currency) == {"USD", "NGN"}
    assert Decimal(str(by_currency["USD"]["balance"])) == Decimal("100.00")
    assert Decimal(str(by_currency["NGN"]["balance"])) == Decimal("50000.00")


def test_balance_is_scoped_to_the_owner(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "scoped", budget="1000", currency="USD"
    )
    _, outsider_headers = register(client, "Outsider", "scoped-outsider@example.com")
    milestone_id = add_priced_milestone(client, contract_id, owner_headers, "100.00")
    submit_and_approve(client, milestone_id, owner_headers, worker_headers)

    assert [row["account_type"] for row in balance(client, owner_headers)] == ["client_payable"]
    assert [row["account_type"] for row in balance(client, worker_headers)] == ["worker_receivable"]
    # Outsiders have no books at all.
    assert balance(client, outsider_headers) == []


def test_contract_ledger_is_restricted_to_parties(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "ledger-authz", budget="1000", currency="USD"
    )
    _, outsider_headers = register(client, "Outsider", "ledger-authz-outsider@example.com")
    milestone_id = add_priced_milestone(client, contract_id, owner_headers, "100.00")
    submit_and_approve(client, milestone_id, owner_headers, worker_headers)

    for headers in (owner_headers, worker_headers):
        assert client.get(
            f"/contracts/{contract_id}/ledger", headers=headers
        ).status_code == 200

    assert client.get(
        f"/contracts/{contract_id}/ledger", headers=outsider_headers
    ).status_code == 403
    assert client.get(f"/contracts/{contract_id}/ledger").status_code == 401
    assert client.get("/contracts/9999/ledger", headers=owner_headers).status_code == 404
    assert client.get("/ledger/balance").status_code == 401


def test_failed_review_posts_no_ledger_entries(client_and_db, monkeypatch):
    client, SessionLocal = client_and_db
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "ledger-rollback", budget="1000", currency="USD"
    )
    milestone_id = add_priced_milestone(client, contract_id, owner_headers, "100.00")

    submit = client.post(
        f"/milestones/{milestone_id}/submit",
        headers=worker_headers,
        json={"note": "Here is the completed work."},
    )
    assert submit.status_code == 200

    def fail_commit(self):
        raise SQLAlchemyError("Sensitive database details")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = client.post(
        f"/milestones/{milestone_id}/review",
        headers=owner_headers,
        json={"decision": "approve", "payment_token": "tok_ok"},
    )
    assert response.status_code == 503

    monkeypatch.undo()

    db = SessionLocal()
    try:
        # Approval and accrual rolled back together: no transaction, no
        # entries, and not even the accounts survived.
        assert db.query(LedgerTransaction).count() == 0
        assert db.query(LedgerEntry).count() == 0
        assert db.query(LedgerAccount).count() == 0
    finally:
        db.close()

    # And the milestone is still submitted, ready to be reviewed again.
    detail = client.get(f"/contracts/{contract_id}", headers=owner_headers).json()
    assert detail["milestones"][0]["status"] == "submitted"


def test_all_ledger_entries_sum_to_zero_globally(client_and_db, monkeypatch):
    client, SessionLocal = client_and_db
    monkeypatch.setattr(ledger_service, "PLATFORM_FEE_PERCENT", Decimal("10"))

    owner_id, owner_headers = register(client, "Owner", "zero-owner@example.com")
    worker_id, worker_headers = register(client, "Worker", "zero-worker@example.com")

    for currency, amount in (("USD", "100.00"), ("NGN", "50000.00")):
        contract_id = hire(client, owner_headers, worker_headers, currency=currency)
        milestone_id = add_priced_milestone(client, contract_id, owner_headers, amount)
        submit_and_approve(client, milestone_id, owner_headers, worker_headers)

    db = SessionLocal()
    try:
        total = db.query(func.coalesce(func.sum(LedgerEntry.amount), 0)).scalar()
        assert total == 0
    finally:
        db.close()


def test_accrual_is_idempotent_at_the_service_level(client_and_db):
    client, SessionLocal = client_and_db
    owner_id, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "idempotent", budget="1000", currency="USD"
    )
    milestone_id = add_priced_milestone(client, contract_id, owner_headers, "100.00")
    submit_and_approve(client, milestone_id, owner_headers, worker_headers)

    db = SessionLocal()
    try:
        milestone = db.query(Milestone).filter_by(id=milestone_id).one()
        contract = db.query(Contract).filter_by(id=contract_id).one()

        first = ledger_service.post_accrual(
            db, milestone=milestone, contract=contract, actor_id=owner_id
        )
        second = ledger_service.post_accrual(
            db, milestone=milestone, contract=contract, actor_id=owner_id
        )
        db.commit()

        # The retry returned the original transaction and posted nothing new.
        assert first.id == second.id
        # Accrual + charge settlement (ADR-012), and nothing more.
        assert db.query(LedgerTransaction).count() == 2
        assert db.query(LedgerEntry).count() == 4
    finally:
        db.close()
