"""Signed work receipts: issuance, privacy, public verification, tamper."""

import hashlib
import json

from app.core.security import create_access_token
from app.models import WorkReceipt
from app.services import receipts as receipts_service


def create_user_headers(client, email, name="Receipt Test User"):
    response = client.post(
        "/auth/register",
        json={
            "full_name": name,
            "email": email,
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


CRITERIA = [
    {"text": "Duplicate records are removed."},
    {"text": "Dates use one consistent format."},
]
EVIDENCE = ["https://files.example.com/cleaned.csv"]


def completed_contract(client, owner, worker):
    """Drive a job with criteria all the way to a completed contract."""
    job = client.post(
        "/jobs",
        headers=owner,
        json={
            "title": "Clean a sales spreadsheet",
            "description": "Dedupe and reformat a messy export.",
            "category": "Data Entry",
            "criteria": CRITERIA,
        },
    )
    assert job.status_code == 201
    job_id = job.json()["id"]

    application = client.post(
        f"/jobs/{job_id}/applications",
        headers=worker,
        json={"cover_letter": "I have cleaned spreadsheets for two years."},
    )
    assert application.status_code == 201

    accept = client.patch(
        f"/jobs/{job_id}/applications/{application.json()['id']}",
        headers=owner,
        json={"status": "accepted"},
    )
    assert accept.status_code == 200

    contracts = client.get("/contracts", headers=owner).json()
    contract = next(c for c in contracts if c["job_id"] == job_id)

    milestone = client.post(
        f"/contracts/{contract['id']}/milestones",
        headers=owner,
        json={"title": "Cleaned file", "amount": "100.00"},
    )
    assert milestone.status_code == 201
    milestone_id = milestone.json()["id"]

    submit = client.post(
        f"/milestones/{milestone_id}/submit",
        headers=worker,
        json={"note": "Work is complete.", "evidence": EVIDENCE},
    )
    assert submit.status_code == 200

    approve = client.post(
        f"/milestones/{milestone_id}/review",
        headers=owner,
        json={"decision": "approve", "payment_token": "tok_test"},
    )
    assert approve.status_code == 200

    complete = client.post(
        f"/contracts/{contract['id']}/complete", headers=owner
    )
    assert complete.status_code == 200
    return contract["id"]


# --- Pure-function units (deterministic, no API) ---


def test_canonicalization_is_deterministic():
    a = {"b": 1, "a": [True, None], "c": {"y": 2, "x": 1}}
    b = {"c": {"x": 1, "y": 2}, "a": [True, None], "b": 1}
    assert receipts_service.canonicalize(a) == receipts_service.canonicalize(b)
    # Tight separators: any whitespace drift would change the hash.
    assert " " not in receipts_service.canonicalize(a)


def test_tampering_changes_the_content_hash():
    original = {"worker": "Wanda", "outcome": {"approved_milestones": 1}}
    altered = {"worker": "Wanda", "outcome": {"approved_milestones": 2}}
    assert receipts_service.hash_canonical(
        receipts_service.canonicalize(original)
    ) != receipts_service.hash_canonical(
        receipts_service.canonicalize(altered)
    )


def test_signature_round_trip_and_wrong_key():
    digest = receipts_service.hash_canonical('{"a":1}')
    signature = receipts_service.sign(digest, b"key-one")
    assert signature == receipts_service.sign(digest, b"key-one")
    assert signature != receipts_service.sign(digest, b"key-two")


# --- API behaviour ---


def test_completion_issues_signed_receipt(client):
    owner = create_user_headers(client, "rc-owner@example.com", "Carl Client")
    worker = create_user_headers(client, "rc-worker@example.com", "Wanda Worker")
    contract_id = completed_contract(client, owner, worker)

    receipt = client.get(f"/contracts/{contract_id}/receipt", headers=owner)
    assert receipt.status_code == 200
    body = receipt.json()
    assert len(body["receipt_uuid"]) == 36
    assert len(body["content_hash"]) == 64
    assert len(body["signature"]) == 64

    payload = body["payload"]
    assert payload["receipt_uuid"] == body["receipt_uuid"]
    assert payload["worker"]["name"] == "Wanda Worker"
    assert payload["job"]["title"] == "Clean a sales spreadsheet"
    # The criteria the worker agreed to are IN the signed payload.
    assert [c["text"] for c in payload["criteria"]] == [
        c["text"] for c in CRITERIA
    ]
    # Evidence is referenced by hash only — the link itself stays private.
    assert payload["milestones"][0]["evidence_hashes"] == [
        hashlib.sha256(EVIDENCE[0].encode("utf-8")).hexdigest()
    ]
    # No client identity, no amounts anywhere in the signed payload.
    raw = json.dumps(payload)
    assert "Carl" not in raw
    assert "client" not in payload
    assert "100" not in raw


def test_verify_endpoint_confirms_genuine_receipt_publicly(client):
    owner = create_user_headers(client, "vf-owner@example.com", "Carl Client")
    worker = create_user_headers(client, "vf-worker@example.com", "Wanda Worker")
    contract_id = completed_contract(client, owner, worker)
    receipt_uuid = client.get(
        f"/contracts/{contract_id}/receipt", headers=owner
    ).json()["receipt_uuid"]

    # No auth header at all — anyone can verify.
    verify = client.get(f"/verify/{receipt_uuid}")
    assert verify.status_code == 200
    body = verify.json()
    assert body["status"] == "valid"
    assert body["worker_name"] == "Wanda Worker"
    assert body["job_title"] == "Clean a sales spreadsheet"
    assert body["job_category"] == "Data Entry"
    assert body["completed_at"] is not None


def test_verify_reports_not_found_for_unknown_uuid(client):
    verify = client.get("/verify/00000000-0000-0000-0000-000000000000")
    assert verify.status_code == 200
    assert verify.json() == {
        "status": "not_found",
        "worker_name": None,
        "job_title": None,
        "job_category": None,
        "completed_at": None,
    }


def test_tampered_receipt_verifies_as_invalid(client_and_db):
    client, session_factory = client_and_db
    owner = create_user_headers(client, "tm-owner@example.com")
    worker = create_user_headers(client, "tm-worker@example.com")
    contract_id = completed_contract(client, owner, worker)
    receipt_uuid = client.get(
        f"/contracts/{contract_id}/receipt", headers=owner
    ).json()["receipt_uuid"]

    # Someone rewrites history directly in the database.
    db = session_factory()
    row = db.query(WorkReceipt).filter_by(receipt_uuid=receipt_uuid).one()
    payload = json.loads(row.payload)
    payload["outcome"]["approved_milestones"] = 99
    row.payload = json.dumps(payload)
    db.commit()
    db.close()

    verify = client.get(f"/verify/{receipt_uuid}")
    assert verify.json()["status"] == "invalid"


def test_receipt_endpoint_is_party_only(client):
    owner = create_user_headers(client, "pp-owner@example.com")
    worker = create_user_headers(client, "pp-worker@example.com")
    outsider = create_user_headers(client, "pp-outsider@example.com")
    contract_id = completed_contract(client, owner, worker)

    assert client.get(
        f"/contracts/{contract_id}/receipt", headers=outsider
    ).status_code == 403
    assert client.get(
        f"/contracts/{contract_id}/receipt", headers=worker
    ).status_code == 200


def test_active_contract_has_no_receipt_yet(client):
    owner = create_user_headers(client, "nr-owner@example.com")
    worker = create_user_headers(client, "nr-worker@example.com")

    job = client.post(
        "/jobs",
        headers=owner,
        json={"title": "Ongoing work", "description": "Still in progress."},
    ).json()
    application = client.post(
        f"/jobs/{job['id']}/applications",
        headers=worker,
        json={"cover_letter": "Happy to help with this work."},
    ).json()
    client.patch(
        f"/jobs/{job['id']}/applications/{application['id']}",
        headers=owner,
        json={"status": "accepted"},
    )
    contracts = client.get("/contracts", headers=owner).json()
    contract_id = contracts[0]["id"]

    assert client.get(
        f"/contracts/{contract_id}/receipt", headers=owner
    ).status_code == 404


def test_missing_signing_key_blocks_completion_cleanly(client, monkeypatch):
    owner = create_user_headers(client, "sk-owner@example.com")
    worker = create_user_headers(client, "sk-worker@example.com")

    job = client.post(
        "/jobs",
        headers=owner,
        json={"title": "Keyless work", "description": "Completion will fail."},
    ).json()
    application = client.post(
        f"/jobs/{job['id']}/applications",
        headers=worker,
        json={"cover_letter": "Ready to do this work now."},
    ).json()
    client.patch(
        f"/jobs/{job['id']}/applications/{application['id']}",
        headers=owner,
        json={"status": "accepted"},
    )
    contract_id = client.get("/contracts", headers=owner).json()[0]["id"]

    monkeypatch.delenv("RECEIPT_SIGNING_KEY")
    complete = client.post(f"/contracts/{contract_id}/complete", headers=owner)
    assert complete.status_code == 503
    assert "RECEIPT_SIGNING_KEY" in complete.json()["detail"]

    # The completion rolled back with the receipt: still active, and a
    # retry with the key restored succeeds.
    monkeypatch.setenv("RECEIPT_SIGNING_KEY", "test-only-signing-key")
    retry = client.post(f"/contracts/{contract_id}/complete", headers=owner)
    assert retry.status_code == 200
    assert retry.json()["status"] == "completed"


def test_receipts_me_lists_only_own_history(client):
    owner = create_user_headers(client, "me-owner@example.com")
    worker = create_user_headers(client, "me-worker@example.com", "Wanda Worker")
    other = create_user_headers(client, "me-other@example.com")
    contract_id = completed_contract(client, owner, worker)

    mine = client.get("/receipts/me", headers=worker)
    assert mine.status_code == 200
    rows = mine.json()
    assert len(rows) == 1
    assert rows[0]["contract_id"] == contract_id
    assert rows[0]["job_title"] == "Clean a sales spreadsheet"
    assert rows[0]["completed_at"] is not None

    # The client and a third party have no worker receipts.
    assert client.get("/receipts/me", headers=owner).json() == []
    assert client.get("/receipts/me", headers=other).json() == []
