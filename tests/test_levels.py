"""Worker levels 0-3: computed from verified receipts, explainable,
and enforced when applying to level-gated jobs."""

from app.core.security import create_access_token


def create_user_headers(client, email, name="Level Test User"):
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


def complete_one_contract(client, owner, worker, title):
    """One full cycle: job -> apply -> accept -> milestone -> submit ->
    approve -> complete. Returns the contract id (i.e. one receipt)."""
    job = client.post(
        "/jobs",
        headers=owner,
        json={"title": title, "description": f"Work for {title}."},
    )
    assert job.status_code == 201
    job_id = job.json()["id"]

    application = client.post(
        f"/jobs/{job_id}/applications",
        headers=worker,
        json={"cover_letter": "I can do this work reliably."},
    )
    assert application.status_code == 201

    accept = client.patch(
        f"/jobs/{job_id}/applications/{application.json()['id']}",
        headers=owner,
        json={"status": "accepted"},
    )
    assert accept.status_code == 200

    contract = next(
        c for c in client.get("/contracts", headers=owner).json()
        if c["job_id"] == job_id
    )
    milestone = client.post(
        f"/contracts/{contract['id']}/milestones",
        headers=owner,
        json={"title": "Deliverable", "amount": "50.00"},
    )
    assert milestone.status_code == 201

    submit = client.post(
        f"/milestones/{milestone.json()['id']}/submit",
        headers=worker,
        json={"note": "Work is complete.", "evidence": ["done.txt"]},
    )
    assert submit.status_code == 200

    approve = client.post(
        f"/milestones/{milestone.json()['id']}/review",
        headers=owner,
        json={"decision": "approve", "payment_token": "tok_test"},
    )
    assert approve.status_code == 200

    complete = client.post(f"/contracts/{contract['id']}/complete", headers=owner)
    assert complete.status_code == 200
    return contract["id"]


def complete_for_clients(client, worker, n_clients, jobs_per_client, label):
    """Complete jobs_per_client contracts for each of n_clients owners."""
    for i in range(n_clients):
        owner = create_user_headers(client, f"{label}-client{i}@example.com")
        for j in range(jobs_per_client):
            complete_one_contract(
                client, owner, worker, f"{label} job {i}-{j}"
            )


def test_newcomer_is_level_zero_with_clear_next_step(client):
    worker = create_user_headers(client, "lv0@example.com")

    level = client.get("/workers/me/level", headers=worker)
    assert level.status_code == 200
    body = level.json()
    assert body["level"] == 0
    assert body["verified_completions"] == 0
    assert body["distinct_clients"] == 0
    assert body["next_level"]["level"] == 1
    assert body["next_level"]["missing"]


def test_first_receipt_reaches_level_one(client):
    owner = create_user_headers(client, "lv1-client@example.com")
    worker = create_user_headers(client, "lv1-worker@example.com")
    complete_one_contract(client, owner, worker, "First job")

    body = client.get("/workers/me/level", headers=worker).json()
    assert body["level"] == 1
    assert body["verified_completions"] == 1
    assert body["distinct_clients"] == 1


def test_repeat_client_counts_receipts_but_not_breadth(client):
    owner = create_user_headers(client, "rep-client@example.com")
    worker = create_user_headers(client, "rep-worker@example.com")
    for i in range(3):
        complete_one_contract(client, owner, worker, f"Repeat job {i}")

    body = client.get("/workers/me/level", headers=worker).json()
    # 3 receipts but only 1 client: level 2 needs breadth, so still 1.
    assert body["level"] == 1
    assert body["verified_completions"] == 3
    assert body["distinct_clients"] == 1
    assert any("client" in item for item in body["next_level"]["missing"])


def test_level_two_and_three_thresholds(client):
    worker = create_user_headers(client, "lv3-worker@example.com")

    # Level 2: 3 completions across 2 clients (2 + 1).
    complete_for_clients(client, worker, n_clients=1, jobs_per_client=2, label="l2a")
    complete_for_clients(client, worker, n_clients=1, jobs_per_client=1, label="l2b")
    body = client.get("/workers/me/level", headers=worker).json()
    assert body["level"] == 2
    assert body["verified_completions"] == 3
    assert body["distinct_clients"] == 2

    # Level 3: 5 completions across 3 clients (add 2 more, new client).
    complete_for_clients(client, worker, n_clients=1, jobs_per_client=2, label="l3c")
    body = client.get("/workers/me/level", headers=worker).json()
    assert body["level"] == 3
    assert body["verified_completions"] == 5
    assert body["distinct_clients"] == 3
    assert body["next_level"] is None


def test_apply_blocked_below_min_worker_level(client):
    owner = create_user_headers(client, "gate-owner@example.com")
    newcomer = create_user_headers(client, "gate-new@example.com")
    proven = create_user_headers(client, "gate-proven@example.com")
    complete_for_clients(client, proven, n_clients=1, jobs_per_client=1, label="gate")

    job = client.post(
        "/jobs",
        headers=owner,
        json={
            "title": "Delicate migration",
            "description": "Needs someone with a verified completion.",
            "min_worker_level": 1,
        },
    )
    assert job.status_code == 201
    job_id = job.json()["id"]

    blocked = client.post(
        f"/jobs/{job_id}/applications",
        headers=newcomer,
        json={"cover_letter": "I am new but very motivated."},
    )
    assert blocked.status_code == 403
    assert "level" in blocked.json()["detail"].lower()

    allowed = client.post(
        f"/jobs/{job_id}/applications",
        headers=proven,
        json={"cover_letter": "I have verified completions already."},
    )
    assert allowed.status_code == 201


def test_level_endpoint_requires_auth(client):
    assert client.get("/workers/me/level").status_code == 401
