"""Submission records with evidence refs + contract criteria snapshots."""

from app.core.security import create_access_token


def create_user_headers(client, email, name="Submission Test User"):
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


def hired_contract(client, owner, worker, criteria=None):
    """Drive a job all the way to a contract with one milestone."""
    job = client.post(
        "/jobs",
        headers=owner,
        json={
            "title": "Clean a sales spreadsheet",
            "description": "Dedupe and reformat a messy export.",
            "criteria": criteria if criteria is not None else CRITERIA,
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
    return contract, milestone.json()


def test_submit_with_evidence_creates_history_record(client):
    owner = create_user_headers(client, "hist-owner@example.com")
    worker = create_user_headers(client, "hist-worker@example.com")
    _, milestone = hired_contract(client, owner, worker)

    submit = client.post(
        f"/milestones/{milestone['id']}/submit",
        headers=worker,
        json={
            "note": "Cleaned file attached.",
            "evidence": [
                "https://files.example.com/cleaned.csv",
                "commit abc123 on the cleanup script",
            ],
        },
    )
    assert submit.status_code == 200
    assert submit.json()["latest_evidence"] == [
        "https://files.example.com/cleaned.csv",
        "commit abc123 on the cleanup script",
    ]

    history = client.get(
        f"/milestones/{milestone['id']}/submissions", headers=owner
    )
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["note"] == "Cleaned file attached."
    assert rows[0]["evidence"][0].startswith("https://")
    assert rows[0]["review_decision"] is None


def test_submit_evidence_validation(client):
    owner = create_user_headers(client, "eval-owner@example.com")
    worker = create_user_headers(client, "eval-worker@example.com")
    _, milestone = hired_contract(client, owner, worker)
    base = {"note": "Cleaned file attached."}

    for bad_evidence in [["   "], ["x" * 501], [f"ref{i}" for i in range(11)]]:
        response = client.post(
            f"/milestones/{milestone['id']}/submit",
            headers=worker,
            json={**base, "evidence": bad_evidence},
        )
        assert response.status_code == 422, bad_evidence


def test_resubmission_keeps_full_history_and_review_targets(client):
    owner = create_user_headers(client, "rev-owner@example.com")
    worker = create_user_headers(client, "rev-worker@example.com")
    _, milestone = hired_contract(client, owner, worker)
    url = f"/milestones/{milestone['id']}"

    client.post(
        f"{url}/submit",
        headers=worker,
        json={"note": "First attempt.", "evidence": ["v1.csv"]},
    )
    review = client.post(
        f"{url}/review",
        headers=owner,
        json={
            "decision": "request_changes",
            "note": "Dates still inconsistent.",
        },
    )
    assert review.status_code == 200

    client.post(
        f"{url}/submit",
        headers=worker,
        json={"note": "Second attempt.", "evidence": ["v2.csv"]},
    )

    history = client.get(f"{url}/submissions", headers=worker).json()
    assert len(history) == 2
    first, second = history
    # The review judged the FIRST submission specifically.
    assert first["evidence"] == ["v1.csv"]
    assert first["review_decision"] == "changes_requested"
    assert first["review_note"] == "Dates still inconsistent."
    assert second["evidence"] == ["v2.csv"]
    assert second["review_decision"] is None


def test_approval_marks_submission_approved(client):
    owner = create_user_headers(client, "appr-owner@example.com")
    worker = create_user_headers(client, "appr-worker@example.com")
    _, milestone = hired_contract(client, owner, worker)
    url = f"/milestones/{milestone['id']}"

    client.post(
        f"{url}/submit",
        headers=worker,
        json={"note": "Work is complete.", "evidence": ["final.csv"]},
    )
    approve = client.post(
        f"{url}/review",
        headers=owner,
        json={"decision": "approve", "payment_token": "tok_test"},
    )
    assert approve.status_code == 200

    history = client.get(f"{url}/submissions", headers=owner).json()
    assert history[0]["review_decision"] == "approved"


def test_submissions_history_is_party_only(client):
    owner = create_user_headers(client, "priv-owner@example.com")
    worker = create_user_headers(client, "priv-worker@example.com")
    outsider = create_user_headers(client, "priv-outsider@example.com")
    _, milestone = hired_contract(client, owner, worker)

    client.post(
        f"/milestones/{milestone['id']}/submit",
        headers=worker,
        json={"note": "Work is complete.", "evidence": ["internal-link"]},
    )

    response = client.get(
        f"/milestones/{milestone['id']}/submissions", headers=outsider
    )
    assert response.status_code == 403


def test_contract_carries_criteria_snapshot_from_hire_time(client):
    owner = create_user_headers(client, "snap-owner@example.com")
    worker = create_user_headers(client, "snap-worker@example.com")
    contract, _ = hired_contract(client, owner, worker)

    assert [c["text"] for c in contract["criteria_snapshot"]] == [
        c["text"] for c in CRITERIA
    ]
    assert all(c["required"] for c in contract["criteria_snapshot"])


def test_contract_without_criteria_snapshots_empty_list(client):
    owner = create_user_headers(client, "snapnone-owner@example.com")
    worker = create_user_headers(client, "snapnone-worker@example.com")
    contract, _ = hired_contract(client, owner, worker, criteria=[])

    assert contract["criteria_snapshot"] == []


def test_milestone_without_submissions_reports_empty_evidence(client):
    owner = create_user_headers(client, "empty-owner@example.com")
    worker = create_user_headers(client, "empty-worker@example.com")
    _, milestone = hired_contract(client, owner, worker)

    assert milestone["latest_evidence"] == []
    history = client.get(
        f"/milestones/{milestone['id']}/submissions", headers=owner
    ).json()
    assert history == []
