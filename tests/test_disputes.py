from decimal import Decimal

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token
from app.models import (
    Dispute,
    LedgerAccount,
    LedgerEntry,
    LedgerTransaction,
    User,
)
from app.services import ledger as ledger_service

VALID_REASON = "The delivered work does not match the agreed requirements."
RESOLUTION_NOTE = "Resolved after reviewing the evidence from both sides."


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


def make_admin(client, SessionLocal, email):
    user_id, _ = register(client, "Admin User", email)
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.id == user_id).first()
        admin.is_admin = True
        db.commit()
    finally:
        db.close()
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


def approve_milestone(client, milestone_id, owner_headers):
    response = client.post(
        f"/milestones/{milestone_id}/review",
        headers=owner_headers,
        json={"decision": "approve", "payment_token": "tok_ok"},
    )
    assert response.status_code == 200


def raise_dispute(client, contract_id, headers, **overrides):
    payload = {"reason": VALID_REASON}
    payload.update(overrides)
    return client.post(
        f"/contracts/{contract_id}/disputes", headers=headers, json=payload
    )


def resolve(client, dispute_id, admin_headers, resolution):
    return client.post(
        f"/admin/disputes/{dispute_id}/resolve",
        headers=admin_headers,
        json={"resolution": resolution, "note": RESOLUTION_NOTE},
    )


def balance_for(client, headers, account_type):
    response = client.get("/ledger/balance", headers=headers)
    assert response.status_code == 200
    for row in response.json():
        if row["account_type"] == account_type:
            return Decimal(str(row["balance"]))
    return Decimal("0")


def contract_status(client, contract_id, headers):
    response = client.get(f"/contracts/{contract_id}", headers=headers)
    assert response.status_code == 200
    return response.json()["status"]


def get_milestone(client, contract_id, headers, index=0):
    response = client.get(f"/contracts/{contract_id}", headers=headers)
    assert response.status_code == 200
    return response.json()["milestones"][index]


# --- Raising disputes ----------------------------------------------------


def test_raise_by_either_party_freezes_the_contract(client):
    _, owner_headers = register(client, "Owner", "rp-owner@example.com")
    worker_id, worker_headers = register(client, "Worker", "rp-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)

    raised = raise_dispute(client, contract_id, worker_headers)

    assert raised.status_code == 201
    dispute = raised.json()
    assert dispute["status"] == "open"
    assert dispute["raised_by"] == worker_id
    assert dispute["reason"] == VALID_REASON
    assert dispute["resolution"] is None
    assert dispute["resolved_by"] is None
    assert contract_status(client, contract_id, owner_headers) == "disputed"

    # Both parties can list the dispute; the raise is on the audit trail.
    disputes = client.get(
        f"/contracts/{contract_id}/disputes", headers=owner_headers
    ).json()
    assert [row["id"] for row in disputes] == [dispute["id"]]
    events = client.get(
        f"/contracts/{contract_id}/events", headers=owner_headers
    ).json()
    raised_events = [e for e in events if e["event_type"] == "dispute_raised"]
    assert len(raised_events) == 1
    assert raised_events[0]["actor_id"] == worker_id
    assert raised_events[0]["note"] == VALID_REASON


def test_dispute_freezes_all_contract_mutations(client):
    _, owner_headers = register(client, "Owner", "freeze-owner@example.com")
    _, worker_headers = register(client, "Worker", "freeze-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)

    assert raise_dispute(client, contract_id, owner_headers).status_code == 201

    assert client.post(
        f"/milestones/{milestone_id}/submit",
        headers=worker_headers,
        json={"note": "Trying to submit during a dispute."},
    ).status_code == 400
    assert client.post(
        f"/contracts/{contract_id}/milestones",
        headers=owner_headers,
        json={"title": "Second deliverable", "amount": "50.00"},
    ).status_code == 400
    assert client.post(
        f"/contracts/{contract_id}/complete", headers=owner_headers
    ).status_code == 400
    assert client.post(
        f"/contracts/{contract_id}/cancel", headers=owner_headers
    ).status_code == 400
    # One open dispute at a time (application-level rule).
    assert raise_dispute(client, contract_id, worker_headers).status_code == 400


def test_raise_requires_a_substantive_reason(client):
    _, owner_headers = register(client, "Owner", "reason-owner@example.com")
    _, worker_headers = register(client, "Worker", "reason-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)

    assert (
        raise_dispute(client, contract_id, owner_headers, reason="too short")
        .status_code
        == 422
    )
    assert (
        client.post(
            f"/contracts/{contract_id}/disputes",
            headers=owner_headers,
            json={},
        ).status_code
        == 422
    )


def test_milestone_reference_must_belong_to_the_contract(client):
    _, owner_headers = register(client, "Owner", "ref-owner@example.com")
    _, worker_headers = register(client, "Worker", "ref-worker@example.com")
    _, other_worker_headers = register(
        client, "Worker Two", "ref-worker-2@example.com"
    )
    contract_id = hired_contract(client, owner_headers, worker_headers)
    other_contract_id = hired_contract(client, owner_headers, other_worker_headers)
    foreign_milestone_id = add_priced_milestone(
        client, other_contract_id, owner_headers
    )

    response = raise_dispute(
        client, contract_id, owner_headers, milestone_id=foreign_milestone_id
    )

    assert response.status_code == 400


def test_dispute_access_control(client):
    _, owner_headers = register(client, "Owner", "ac-owner@example.com")
    _, worker_headers = register(client, "Worker", "ac-worker@example.com")
    _, outsider_headers = register(client, "Outsider", "ac-outsider@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)

    assert raise_dispute(client, contract_id, outsider_headers).status_code == 403
    assert (
        client.post(
            f"/contracts/{contract_id}/disputes", json={"reason": VALID_REASON}
        ).status_code
        == 401
    )
    assert (
        client.get(
            f"/contracts/{contract_id}/disputes", headers=outsider_headers
        ).status_code
        == 403
    )
    assert client.get(f"/contracts/{contract_id}/disputes").status_code == 401
    assert (
        client.get(
            f"/contracts/{contract_id}/disputes", headers=owner_headers
        ).json()
        == []
    )


# --- Resolution ----------------------------------------------------------


def test_worker_favored_resolution_force_approves_and_accrues(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "wf-owner@example.com")
    _, worker_headers = register(client, "Worker", "wf-worker@example.com")
    admin_id, admin_headers = make_admin(
        client, SessionLocal, "wf-admin@example.com"
    )
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)
    submit_milestone(client, milestone_id, worker_headers)

    dispute = raise_dispute(
        client, contract_id, owner_headers, milestone_id=milestone_id
    ).json()

    resolved = resolve(client, dispute["id"], admin_headers, "worker_favored")

    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolution"] == "worker_favored"
    assert body["resolution_note"] == RESOLUTION_NOTE
    assert body["resolved_by"] == admin_id
    assert body["resolved_at"] is not None

    # Milestone force-approved; the accrual stands; the contract resumes.
    assert get_milestone(client, contract_id, owner_headers)["status"] == "approved"
    assert contract_status(client, contract_id, owner_headers) == "active"
    assert balance_for(client, owner_headers, "client_payable") == Decimal("100")
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("100")

    # The evidence trail attributes the force-approval to the admin.
    events = client.get(
        f"/contracts/{contract_id}/events", headers=owner_headers
    ).json()
    approvals = [e for e in events if e["event_type"] == "review_approved"]
    assert approvals[-1]["actor_id"] == admin_id
    resolutions = [e for e in events if e["event_type"] == "dispute_resolved"]
    assert len(resolutions) == 1
    assert resolutions[0]["actor_id"] == admin_id
    assert resolutions[0]["note"].startswith("worker_favored")


def test_client_favored_resolution_cancels_and_reverses(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "cf-owner@example.com")
    _, worker_headers = register(client, "Worker", "cf-worker@example.com")
    _, admin_headers = make_admin(client, SessionLocal, "cf-admin@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)
    submit_milestone(client, milestone_id, worker_headers)
    approve_milestone(client, milestone_id, owner_headers)

    # The charge settled at approval (ADR-012): the client's payable is
    # already cleared and the worker's receivable is cash-backed.
    assert balance_for(client, owner_headers, "client_payable") == Decimal("0")
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("100")

    dispute = raise_dispute(
        client, contract_id, worker_headers, milestone_id=milestone_id
    ).json()
    resolved = resolve(client, dispute["id"], admin_headers, "client_favored")

    assert resolved.status_code == 200
    assert resolved.json()["resolution"] == "client_favored"
    assert contract_status(client, contract_id, owner_headers) == "cancelled"

    # The reversal wipes the obligation, but the milestone stays
    # approved — history is not rewritten (ADR-011).
    assert balance_for(client, owner_headers, "client_payable") == Decimal("0")
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("0")
    assert get_milestone(client, contract_id, owner_headers)["status"] == "approved"

    # The ledger shows the accrual and the charge, plus their
    # mirror-image reversals — and the refund returned the cash, so
    # every balance is back to zero.
    db = SessionLocal()
    try:
        transactions = (
            db.query(LedgerTransaction)
            .filter(LedgerTransaction.contract_id == contract_id)
            .all()
        )
        assert sorted(txn.type for txn in transactions) == [
            "accrual",
            "reversal",
            "reversal",
            "settlement",
        ]
        for txn in transactions:
            assert sum(entry.amount for entry in txn.entries) == Decimal("0")

        cash_account = (
            db.query(LedgerAccount)
            .filter(
                LedgerAccount.account_type == "platform_cash",
                LedgerAccount.currency == "USD",
            )
            .one()
        )
        cash_total = db.query(
            func.coalesce(func.sum(LedgerEntry.amount), 0)
        ).filter(LedgerEntry.account_id == cash_account.id).scalar()
        assert cash_total == Decimal("0")
    finally:
        db.close()


def test_dismissed_resolution_resumes_without_changes(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "dm-owner@example.com")
    _, worker_headers = register(client, "Worker", "dm-worker@example.com")
    _, admin_headers = make_admin(client, SessionLocal, "dm-admin@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)
    submit_milestone(client, milestone_id, worker_headers)

    dispute = raise_dispute(
        client, contract_id, owner_headers, milestone_id=milestone_id
    ).json()
    resolved = resolve(client, dispute["id"], admin_headers, "dismissed")

    assert resolved.status_code == 200
    assert resolved.json()["resolution"] == "dismissed"
    assert contract_status(client, contract_id, owner_headers) == "active"
    assert get_milestone(client, contract_id, owner_headers)["status"] == "submitted"
    assert balance_for(client, owner_headers, "client_payable") == Decimal("0")

    # Work flows again immediately after a dismissal — and the approval
    # charges the client at once (ADR-012), so the payable clears.
    approve_milestone(client, milestone_id, owner_headers)
    assert balance_for(client, owner_headers, "client_payable") == Decimal("0")
    assert balance_for(client, worker_headers, "worker_receivable") == Decimal("100")


def test_resolution_is_final(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "fin-owner@example.com")
    _, worker_headers = register(client, "Worker", "fin-worker@example.com")
    _, admin_headers = make_admin(client, SessionLocal, "fin-admin@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    dispute = raise_dispute(client, contract_id, owner_headers).json()

    assert resolve(client, dispute["id"], admin_headers, "dismissed").status_code == 200
    assert (
        resolve(client, dispute["id"], admin_headers, "worker_favored").status_code
        == 400
    )


def test_admin_endpoints_require_admin(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "az-owner@example.com")
    _, worker_headers = register(client, "Worker", "az-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    dispute = raise_dispute(client, contract_id, owner_headers).json()

    assert client.get("/admin/disputes", headers=owner_headers).status_code == 403
    assert (
        resolve(client, dispute["id"], owner_headers, "dismissed").status_code
        == 403
    )
    assert client.get("/admin/disputes").status_code == 401

    _, admin_headers = make_admin(client, SessionLocal, "az-admin@example.com")
    listed = client.get("/admin/disputes", headers=admin_headers)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [dispute["id"]]
    assert (
        client.get(
            "/admin/disputes",
            headers=admin_headers,
            params={"dispute_status": "resolved"},
        ).json()
        == []
    )
    assert (
        client.get(
            "/admin/disputes",
            headers=admin_headers,
            params={"dispute_status": "bogus"},
        ).status_code
        == 422
    )
    assert resolve(client, 9999, admin_headers, "dismissed").status_code == 404


# --- Database-level guarantees --------------------------------------------


def test_one_open_dispute_per_contract_enforced_by_database(client_and_db):
    client, SessionLocal = client_and_db
    owner_id, owner_headers = register(client, "Owner", "db-owner@example.com")
    _, worker_headers = register(client, "Worker", "db-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    assert raise_dispute(client, contract_id, owner_headers).status_code == 201

    # The partial unique index rejects a second open dispute even if
    # application logic regresses (ADR-011).
    db = SessionLocal()
    try:
        db.add(
            Dispute(
                contract_id=contract_id,
                raised_by=owner_id,
                reason=VALID_REASON,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_reversal_is_idempotent_at_the_service_level(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "ri-owner@example.com")
    _, worker_headers = register(client, "Worker", "ri-worker@example.com")
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)
    submit_milestone(client, milestone_id, worker_headers)
    approve_milestone(client, milestone_id, owner_headers)

    db = SessionLocal()
    try:
        accrual = (
            db.query(LedgerTransaction)
            .filter(LedgerTransaction.type == "accrual")
            .one()
        )
        first = ledger_service.post_reversal(
            db, original=accrual, actor_id=accrual.created_by
        )
        db.commit()
        # A retried call returns the original reversal instead of
        # double-reversing.
        second = ledger_service.post_reversal(
            db, original=accrual, actor_id=accrual.created_by
        )
        db.commit()
        assert second.id == first.id
        # Mirror the dispute path (ADR-012): reverse the charge
        # settlement too, so the client gets their cash back.
        settlement = (
            db.query(LedgerTransaction)
            .filter(LedgerTransaction.type == "settlement")
            .one()
        )
        ledger_service.post_reversal(
            db, original=settlement, actor_id=settlement.created_by
        )
        db.commit()
        assert (
            db.query(LedgerTransaction)
            .filter(LedgerTransaction.type == "reversal")
            .count()
            == 2
        )
    finally:
        db.close()

    assert balance_for(client, owner_headers, "client_payable") == Decimal("0")


def test_admin_listing_embeds_decision_context(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Olivia Owner", "ctx-owner@example.com")
    _, worker_headers = register(
        client, "Wendy Worker", "ctx-worker@example.com"
    )
    contract_id = hired_contract(client, owner_headers, worker_headers)
    milestone_id = add_priced_milestone(client, contract_id, owner_headers)
    submit_milestone(client, milestone_id, worker_headers)
    dispute = raise_dispute(
        client, contract_id, worker_headers, milestone_id=milestone_id
    ).json()

    _, admin_headers = make_admin(client, SessionLocal, "ctx-admin@example.com")
    rows = client.get("/admin/disputes", headers=admin_headers).json()

    # The admin decides without being a party, so the listing carries
    # the job, contract, milestone, and names — not bare ids.
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == dispute["id"]
    assert row["job_title"] == "Build a landing page"
    assert row["contract_status"] == "disputed"
    assert Decimal(str(row["agreed_amount"])) == Decimal("300.00")
    assert row["currency"] == "USD"
    assert row["milestone_title"] == "First deliverable"
    assert row["milestone_status"] == "submitted"
    assert Decimal(str(row["milestone_amount"])) == Decimal("100.00")
    assert row["raised_by_name"] == "Wendy Worker"
    assert row["client_name"] == "Olivia Owner"
    assert row["worker_name"] == "Wendy Worker"


def test_me_response_includes_is_admin(client_and_db):
    client, SessionLocal = client_and_db
    _, plain_headers = register(client, "Plain User", "me-plain@example.com")
    me = client.get("/auth/me", headers=plain_headers).json()
    assert me["is_admin"] is False

    _, admin_headers = make_admin(client, SessionLocal, "me-admin@example.com")
    me = client.get("/auth/me", headers=admin_headers).json()
    assert me["is_admin"] is True
