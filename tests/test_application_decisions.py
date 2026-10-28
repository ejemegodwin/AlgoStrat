from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import JobApplication


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


def create_open_job(client, owner_headers):
    response = client.post(
        "/jobs",
        headers=owner_headers,
        json={
            "title": "Build a company website",
            "description": "Create a professional website for a business.",
        },
    )
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


def application_statuses(client, job_id, owner_headers):
    response = client.get(
        f"/jobs/{job_id}/applications",
        headers=owner_headers,
    )
    assert response.status_code == 200
    return {app["id"]: app["status"] for app in response.json()}


def job_status(client, job_id):
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    return response.json()["status"]


def test_accepting_an_application_closes_the_job(client):
    _, owner_headers = register(client, "Owner", "accept-close-owner@example.com")
    _, worker_headers = register(client, "Worker", "accept-close-worker@example.com")
    job_id = create_open_job(client, owner_headers)
    application_id = apply(client, job_id, worker_headers)

    response = decide(client, job_id, application_id, owner_headers, "accepted")

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert job_status(client, job_id) == "closed"


def test_accepting_an_application_rejects_other_pending_applications(client):
    _, owner_headers = register(client, "Owner", "accept-others-owner@example.com")
    job_id = create_open_job(client, owner_headers)

    workers = []
    for i in range(3):
        _, worker_headers = register(
            client, f"Worker {i}", f"accept-others-worker-{i}@example.com"
        )
        application_id = apply(client, job_id, worker_headers)
        workers.append((worker_headers, application_id))

    # One worker withdraws before the decision; it must stay withdrawn.
    withdraw_response = client.patch(
        f"/applications/{workers[2][1]}/withdraw",
        headers=workers[2][0],
    )
    assert withdraw_response.status_code == 200

    response = decide(client, job_id, workers[0][1], owner_headers, "accepted")

    assert response.status_code == 200
    statuses = application_statuses(client, job_id, owner_headers)
    assert statuses[workers[0][1]] == "accepted"
    assert statuses[workers[1][1]] == "rejected"
    assert statuses[workers[2][1]] == "withdrawn"


def test_cannot_accept_a_second_application_after_hiring(client):
    _, owner_headers = register(client, "Owner", "second-accept-owner@example.com")
    _, worker_headers_1 = register(client, "Worker 1", "second-accept-w1@example.com")
    _, worker_headers_2 = register(client, "Worker 2", "second-accept-w2@example.com")
    job_id = create_open_job(client, owner_headers)
    first_id = apply(client, job_id, worker_headers_1)
    second_id = apply(client, job_id, worker_headers_2)

    first_response = decide(client, job_id, first_id, owner_headers, "accepted")
    assert first_response.status_code == 200

    # The second application was auto-rejected by the hire, so the
    # pending check rejects a repeated decision.
    second_response = decide(client, job_id, second_id, owner_headers, "accepted")
    assert second_response.status_code == 400

    statuses = application_statuses(client, job_id, owner_headers)
    assert statuses[first_id] == "accepted"
    assert statuses[second_id] == "rejected"


def test_cannot_accept_application_for_a_closed_job(client_and_db):
    client, SessionLocal = client_and_db
    _, owner_headers = register(client, "Owner", "closed-accept-owner@example.com")
    _, worker_headers = register(client, "Worker", "closed-accept-worker@example.com")
    job_id = create_open_job(client, owner_headers)
    application_id = apply(client, job_id, worker_headers)

    close_response = client.patch(
        f"/jobs/{job_id}/close",
        headers=owner_headers,
    )
    assert close_response.status_code == 200

    # Closing resolved the application as rejected. Simulate legacy data
    # (a pending application on a closed job) to prove the open-job check
    # still blocks acceptance.
    db = SessionLocal()
    try:
        application = db.query(JobApplication).filter(
            JobApplication.id == application_id
        ).first()
        application.status = "pending"
        db.commit()
    finally:
        db.close()

    response = decide(client, job_id, application_id, owner_headers, "accepted")

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "You can only accept applications for open jobs."
    )


def test_closing_a_job_rejects_its_pending_applications(client):
    _, owner_headers = register(client, "Owner", "close-reject-owner@example.com")
    _, worker_headers = register(client, "Worker", "close-reject-worker@example.com")
    job_id = create_open_job(client, owner_headers)
    application_id = apply(client, job_id, worker_headers)

    response = client.patch(
        f"/jobs/{job_id}/close",
        headers=owner_headers,
    )

    assert response.status_code == 200
    statuses = application_statuses(client, job_id, owner_headers)
    assert statuses[application_id] == "rejected"


def test_rejecting_an_application_keeps_the_job_open(client):
    _, owner_headers = register(client, "Owner", "reject-open-owner@example.com")
    _, worker_headers = register(client, "Worker", "reject-open-worker@example.com")
    job_id = create_open_job(client, owner_headers)
    application_id = apply(client, job_id, worker_headers)

    response = decide(client, job_id, application_id, owner_headers, "rejected")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert job_status(client, job_id) == "open"


def test_failed_accept_leaves_job_and_applications_unchanged(
    client, monkeypatch
):
    _, owner_headers = register(client, "Owner", "rollback-owner@example.com")
    _, worker_headers_1 = register(client, "Worker 1", "rollback-w1@example.com")
    _, worker_headers_2 = register(client, "Worker 2", "rollback-w2@example.com")
    job_id = create_open_job(client, owner_headers)
    first_id = apply(client, job_id, worker_headers_1)
    second_id = apply(client, job_id, worker_headers_2)

    def fail_commit(self):
        raise SQLAlchemyError("Sensitive database details")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = decide(client, job_id, first_id, owner_headers, "accepted")

    assert response.status_code == 503
    assert "Sensitive database details" not in response.text

    monkeypatch.undo()

    # Nothing may be partially applied: job still open, both still pending.
    assert job_status(client, job_id) == "open"
    statuses = application_statuses(client, job_id, owner_headers)
    assert statuses[first_id] == "pending"
    assert statuses[second_id] == "pending"
