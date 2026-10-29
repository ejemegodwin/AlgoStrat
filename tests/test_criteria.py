"""Job acceptance criteria (the verifiable-work thesis foundation).

Criteria are written by the client, visible to applicants, replaceable
while the job is open and contract-free, and locked once work starts.
"""

from app.core.security import create_access_token


def create_user_headers(client, email):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Criteria Test User",
            "email": email,
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def create_job(client, headers, **overrides):
    job_data = {
        "title": "Clean a sales spreadsheet",
        "description": "Dedupe and reformat a messy export.",
    }
    job_data.update(overrides)
    response = client.post("/jobs", headers=headers, json=job_data)
    assert response.status_code == 201
    return response.json()


CRITERIA = [
    {"text": "Duplicate records are removed."},
    {"text": "Dates use one consistent format.", "required": True},
    {"text": "A short explanation is submitted.", "required": False},
]


def test_create_job_with_criteria_preserves_order_and_defaults(client):
    headers = create_user_headers(client, "owner-order@example.com")

    job = create_job(client, headers, criteria=CRITERIA)

    assert [c["text"] for c in job["criteria"]] == [c["text"] for c in CRITERIA]
    assert [c["position"] for c in job["criteria"]] == [0, 1, 2]
    # Omitted "required" defaults to true; explicit false is kept.
    assert [c["required"] for c in job["criteria"]] == [True, True, False]


def test_create_job_without_criteria_returns_empty_list(client):
    headers = create_user_headers(client, "owner-none@example.com")

    job = create_job(client, headers)

    assert job["criteria"] == []


def test_create_job_rejects_whitespace_only_criterion(client):
    headers = create_user_headers(client, "owner-blank@example.com")

    response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Clean a sales spreadsheet",
            "description": "Dedupe and reformat a messy export.",
            "criteria": [{"text": "   "}],
        },
    )

    assert response.status_code == 422


def test_create_job_rejects_overlong_criterion(client):
    headers = create_user_headers(client, "owner-long@example.com")

    response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Clean a sales spreadsheet",
            "description": "Dedupe and reformat a messy export.",
            "criteria": [{"text": "x" * 501}],
        },
    )

    assert response.status_code == 422


def test_create_job_rejects_too_many_criteria(client):
    headers = create_user_headers(client, "owner-many@example.com")

    response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Clean a sales spreadsheet",
            "description": "Dedupe and reformat a messy export.",
            "criteria": [{"text": f"Criterion {i}"} for i in range(21)],
        },
    )

    assert response.status_code == 422


def test_criteria_visible_on_public_job_detail_and_list(client):
    headers = create_user_headers(client, "owner-public@example.com")
    job = create_job(client, headers, criteria=CRITERIA)

    detail = client.get(f"/jobs/{job['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["criteria"]) == 3

    listing = client.get("/jobs")
    assert listing.status_code == 200
    listed = next(j for j in listing.json() if j["id"] == job["id"])
    assert len(listed["criteria"]) == 3


def test_owner_can_replace_criteria_while_open(client):
    headers = create_user_headers(client, "owner-edit@example.com")
    job = create_job(client, headers, criteria=CRITERIA)
    old_ids = {c["id"] for c in job["criteria"]}

    response = client.patch(
        f"/jobs/{job['id']}",
        headers=headers,
        json={"criteria": [{"text": "The only criterion now."}]},
    )

    assert response.status_code == 200
    new_criteria = response.json()["criteria"]
    assert [c["text"] for c in new_criteria] == ["The only criterion now."]
    assert new_criteria[0]["id"] not in old_ids

    # Persisted, not just returned.
    detail = client.get(f"/jobs/{job['id']}").json()
    assert [c["text"] for c in detail["criteria"]] == [
        "The only criterion now."
    ]


def test_non_owner_cannot_edit_criteria(client):
    owner = create_user_headers(client, "owner-protect@example.com")
    intruder = create_user_headers(client, "intruder@example.com")
    job = create_job(client, owner, criteria=CRITERIA)

    response = client.patch(
        f"/jobs/{job['id']}",
        headers=intruder,
        json={"criteria": [{"text": "Weakened criterion."}]},
    )

    assert response.status_code == 403


def test_criteria_uneditable_on_closed_job(client):
    headers = create_user_headers(client, "owner-closed@example.com")
    job = create_job(client, headers, criteria=CRITERIA)
    client.patch(f"/jobs/{job['id']}/close", headers=headers)

    response = client.patch(
        f"/jobs/{job['id']}",
        headers=headers,
        json={"criteria": [{"text": "Too late."}]},
    )

    assert response.status_code == 400


def test_criteria_locked_once_contract_exists(client):
    owner = create_user_headers(client, "owner-locked@example.com")
    worker = create_user_headers(client, "worker-locked@example.com")
    job = create_job(client, owner, criteria=CRITERIA)

    application = client.post(
        f"/jobs/{job['id']}/applications",
        headers=worker,
        json={"cover_letter": "I have cleaned spreadsheets for two years."},
    )
    assert application.status_code == 201

    accept = client.patch(
        f"/jobs/{job['id']}/applications/{application.json()['id']}",
        headers=owner,
        json={"status": "accepted"},
    )
    assert accept.status_code == 200

    response = client.patch(
        f"/jobs/{job['id']}",
        headers=owner,
        json={"criteria": [{"text": "Secretly easier now."}]},
    )

    # Accepting closed the job (single-hire model), so the edit is
    # refused either way — the invariant that matters is below: the
    # agreed criteria can never change once work has started.
    assert response.status_code == 400

    # Untouched: the agreed criteria still stand.
    detail = client.get(f"/jobs/{job['id']}").json()
    assert [c["text"] for c in detail["criteria"]] == [
        c["text"] for c in CRITERIA
    ]


def test_explicit_null_criteria_rejected_on_update(client):
    headers = create_user_headers(client, "owner-null@example.com")
    job = create_job(client, headers, criteria=CRITERIA)

    response = client.patch(
        f"/jobs/{job['id']}", headers=headers, json={"criteria": None}
    )

    assert response.status_code == 422


def test_clearing_criteria_while_open_is_allowed(client):
    headers = create_user_headers(client, "owner-clear@example.com")
    job = create_job(client, headers, criteria=CRITERIA)

    response = client.patch(
        f"/jobs/{job['id']}", headers=headers, json={"criteria": []}
    )

    assert response.status_code == 200
    assert response.json()["criteria"] == []
