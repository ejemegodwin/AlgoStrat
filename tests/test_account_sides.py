"""Account sides (ADR-018): account_type gates who may act on which
side of the marketplace. client posts jobs, worker applies and keeps
a profile, both do both. There is no default — registration requires
the choice."""

from app.core.security import create_access_token


def register(client, full_name, email, account_type="both"):
    response = client.post(
        "/auth/register",
        json={
            "full_name": full_name,
            "email": email,
            "password": "SecurePass123!",
            "account_type": account_type,
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    return user_id, {"Authorization": f"Bearer {create_access_token(user_id)}"}


def test_registration_requires_a_side(client):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "No Side User",
            "email": "noside@example.com",
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 422


def test_registration_rejects_an_unknown_side(client):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Bad Side User",
            "email": "badside@example.com",
            "password": "SecurePass123!",
            "account_type": "individual",
        },
    )
    assert response.status_code == 422


def test_client_cannot_apply(client):
    _, owner_headers = register(client, "Owner", "side-owner@example.com")
    _, client_headers = register(
        client, "Client Two", "side-client2@example.com", account_type="client"
    )
    job = client.post(
        "/jobs",
        headers=owner_headers,
        json={
            "title": "Side gating test job",
            "description": "A job for testing account side gating.",
            "budget": "100.00",
            "currency": "USD",
        },
    )
    assert job.status_code == 201

    response = client.post(
        f"/jobs/{job.json()['id']}/applications",
        headers=client_headers,
        json={"cover_letter": "A client trying to work the other side."},
    )
    assert response.status_code == 403
    assert "worker" in response.json()["detail"]


def test_worker_cannot_post_jobs(client):
    _, worker_headers = register(
        client, "Worker", "side-worker@example.com", account_type="worker"
    )
    response = client.post(
        "/jobs",
        headers=worker_headers,
        json={
            "title": "Worker trying to post",
            "description": "This should be rejected with a 403.",
            "budget": "100.00",
            "currency": "USD",
        },
    )
    assert response.status_code == 403
    assert "client" in response.json()["detail"]


def test_worker_only_endpoints_reject_clients(client):
    _, client_headers = register(
        client, "Client", "side-client@example.com", account_type="client"
    )

    response = client.get("/jobs/recommended", headers=client_headers)
    assert response.status_code == 403

    response = client.put(
        "/profiles/me/worker",
        headers=client_headers,
        json={"availability": "available", "skills": ["python"]},
    )
    assert response.status_code == 403


def test_both_can_act_on_either_side(client):
    _, both_headers = register(
        client, "Both User", "side-both@example.com", account_type="both"
    )
    _, owner_headers = register(client, "Owner", "side-owner2@example.com")

    job = client.post(
        "/jobs",
        headers=both_headers,
        json={
            "title": "Posted by a both account",
            "description": "Both-side users may post jobs.",
            "budget": "50.00",
            "currency": "USD",
        },
    )
    assert job.status_code == 201

    other_job = client.post(
        "/jobs",
        headers=owner_headers,
        json={
            "title": "Someone else's job",
            "description": "Posted by a plain owner for the both user.",
            "budget": "50.00",
            "currency": "USD",
        },
    )
    response = client.post(
        f"/jobs/{other_job.json()['id']}/applications",
        headers=both_headers,
        json={"cover_letter": "A both account applying to work."},
    )
    assert response.status_code == 201

    assert client.get("/jobs/recommended", headers=both_headers).status_code == 200
