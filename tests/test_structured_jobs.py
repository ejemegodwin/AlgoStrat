"""Structured jobs (type, mode, deadline, level gate) and the
application proposal fields (price, currency, estimated days)."""

from app.core.security import create_access_token


def create_user_headers(client, email):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Structured Test User",
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


CRITERION = [{"text": "Duplicate records are removed."}]


def test_job_defaults_are_standard_remote_level_zero(client):
    headers = create_user_headers(client, "defaults@example.com")

    job = create_job(client, headers)

    assert job["job_type"] == "standard"
    assert job["work_mode"] == "remote"
    assert job["min_worker_level"] == 0
    assert job["deadline"] is None


def test_create_job_with_all_structured_fields(client):
    headers = create_user_headers(client, "full@example.com")

    job = create_job(
        client,
        headers,
        job_type="starter_task",
        work_mode="in_person",
        deadline="2026-12-01T17:00:00Z",
        min_worker_level=2,
        criteria=CRITERION,
    )

    assert job["job_type"] == "starter_task"
    assert job["work_mode"] == "in_person"
    assert job["min_worker_level"] == 2
    assert job["deadline"] is not None


def test_invalid_job_type_mode_and_level_rejected(client):
    headers = create_user_headers(client, "invalid@example.com")

    for overrides in [
        {"job_type": "gig"},
        {"work_mode": "hybrid"},
        {"min_worker_level": 4},
        {"min_worker_level": -1},
    ]:
        response = client.post(
            "/jobs",
            headers=headers,
            json={
                "title": "Clean a sales spreadsheet",
                "description": "Dedupe and reformat a messy export.",
                **overrides,
            },
        )
        assert response.status_code == 422, overrides


def test_starter_task_requires_criteria(client):
    headers = create_user_headers(client, "starter@example.com")

    response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Clean a sales spreadsheet",
            "description": "Dedupe and reformat a messy export.",
            "job_type": "starter_task",
        },
    )

    assert response.status_code == 422
    assert "criterion" in response.json()["detail"].lower()


def test_placement_check_requires_criteria(client):
    headers = create_user_headers(client, "placement@example.com")

    response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Spreadsheet skills check",
            "description": "A controlled assessment task.",
            "job_type": "placement_check",
        },
    )

    assert response.status_code == 422


def test_edit_into_starter_task_without_criteria_rejected(client):
    headers = create_user_headers(client, "edit-type@example.com")
    job = create_job(client, headers)  # standard, no criteria

    response = client.patch(
        f"/jobs/{job['id']}", headers=headers, json={"job_type": "starter_task"}
    )

    assert response.status_code == 422


def test_clearing_criteria_on_starter_task_rejected(client):
    headers = create_user_headers(client, "edit-clear@example.com")
    job = create_job(
        client, headers, job_type="starter_task", criteria=CRITERION
    )

    response = client.patch(
        f"/jobs/{job['id']}", headers=headers, json={"criteria": []}
    )

    assert response.status_code == 422
    # Still a starter task with its original criterion intact.
    detail = client.get(f"/jobs/{job['id']}").json()
    assert detail["job_type"] == "starter_task"
    assert len(detail["criteria"]) == 1


def test_deadline_can_be_set_and_cleared(client):
    headers = create_user_headers(client, "deadline@example.com")
    job = create_job(client, headers)

    updated = client.patch(
        f"/jobs/{job['id']}",
        headers=headers,
        json={"deadline": "2026-12-01T17:00:00Z"},
    )
    assert updated.status_code == 200
    assert updated.json()["deadline"] is not None

    cleared = client.patch(
        f"/jobs/{job['id']}", headers=headers, json={"deadline": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["deadline"] is None


def test_application_with_proposal_fields(client):
    owner = create_user_headers(client, "prop-owner@example.com")
    worker = create_user_headers(client, "prop-worker@example.com")
    job = create_job(client, owner)

    response = client.post(
        f"/jobs/{job['id']}/applications",
        headers=worker,
        json={
            "cover_letter": "I can deliver this quickly and cleanly.",
            "proposed_price": "120.50",
            "proposed_currency": "ngn",
            "estimated_days": 4,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["proposed_price"] == "120.50"
    assert body["proposed_currency"] == "NGN"
    assert body["estimated_days"] == 4


def test_application_proposal_defaults_to_none(client):
    owner = create_user_headers(client, "propdef-owner@example.com")
    worker = create_user_headers(client, "propdef-worker@example.com")
    job = create_job(client, owner)

    response = client.post(
        f"/jobs/{job['id']}/applications",
        headers=worker,
        json={"cover_letter": "Happy to take this on as listed."},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["proposed_price"] is None
    assert body["proposed_currency"] is None
    assert body["estimated_days"] is None


def test_application_proposal_validation(client):
    owner = create_user_headers(client, "propval-owner@example.com")
    worker = create_user_headers(client, "propval-worker@example.com")
    job = create_job(client, owner)
    base = {"cover_letter": "I can deliver this quickly and cleanly."}

    for bad in [
        {"proposed_price": "0"},
        {"proposed_price": "-5"},
        {"proposed_currency": "XX1"},
        {"estimated_days": 0},
        {"estimated_days": 400},
    ]:
        response = client.post(
            f"/jobs/{job['id']}/applications",
            headers=worker,
            json={**base, **bad},
        )
        assert response.status_code == 422, bad
