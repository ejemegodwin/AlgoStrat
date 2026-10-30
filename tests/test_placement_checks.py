"""Placement checks: public listing, worker attempts, admin review."""

import json
from datetime import datetime, timezone

import pytest

from app.core.security import create_access_token
from app.models import PlacementCheck, PlacementVariant, PlacementAttempt, ProfileTag, User


def _create_user(client, email, name="Test User", account_type="worker"):
    response = client.post(
        "/auth/register",
        json={
            "full_name": name,
            "email": email,
            "password": "SecurePass123!",
            "account_type": account_type,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _headers(user_id):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _make_admin(client_and_db, user_id):
    _, SessionLocal = client_and_db
    db = SessionLocal()
    admin_user = db.query(User).filter(User.id == user_id).first()
    admin_user.is_admin = True
    db.commit()
    db.close()


@pytest.fixture
def seeded_checks(client_and_db):
    """Seed two placement checks with variants directly into the DB."""
    _, SessionLocal = client_and_db
    db = SessionLocal()

    check_py = PlacementCheck(
        skill="python",
        title="Basic Python",
        description="Write a function that returns the sum of a list.",
        learning_resources="https://docs.python.org/3/tutorial/",
        reviewer_guidance="Check for correct output and clean code.",
        created_at=datetime.now(timezone.utc),
    )
    db.add(check_py)
    db.flush()

    v1 = PlacementVariant(
        check_id=check_py.id,
        position=0,
        prompt="Implement sum_list(items): return the sum of all items.",
        criteria=json.dumps(["Returns correct sum", "Handles empty list", "No built-in sum"]),
        reviewer_notes="Use a loop, not sum().",
    )
    v2 = PlacementVariant(
        check_id=check_py.id,
        position=1,
        prompt="Implement sum_list(items): same task, different variant.",
        criteria=json.dumps(["Returns correct sum", "Handles empty list"]),
    )
    db.add_all([v1, v2])

    check_js = PlacementCheck(
        skill="javascript",
        title="JS Fundamentals",
        description="Write a function that filters even numbers.",
        learning_resources="https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide",
        reviewer_guidance="Check edge cases.",
        created_at=datetime.now(timezone.utc),
    )
    db.add(check_js)
    db.flush()

    v_js = PlacementVariant(
        check_id=check_js.id,
        position=0,
        prompt="Implement filterEven(numbers): return only even numbers.",
        criteria=json.dumps(["Returns only even numbers", "Handles empty input"]),
    )
    db.add(v_js)

    db.commit()
    py_id, js_id = check_py.id, check_js.id
    db.close()
    return py_id, js_id


# --- Public endpoints ---

def test_list_placement_checks_public(client_and_db, seeded_checks):
    client, _ = client_and_db
    response = client.get("/placement-checks")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    skills = [c["skill"] for c in body]
    assert "python" in skills and "javascript" in skills


def test_list_placement_checks_filter_by_skill(client_and_db, seeded_checks):
    client, _ = client_and_db
    response = client.get("/placement-checks?skill=pyth")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["skill"] == "python"


def test_get_placement_check_by_skill(client_and_db, seeded_checks):
    client, _ = client_and_db
    response = client.get("/placement-checks/python")
    assert response.status_code == 200
    body = response.json()
    assert body["skill"] == "python"
    assert body["title"] == "Basic Python"
    assert len(body["variants"]) == 2
    assert "criteria" in body["variants"][0]


def test_get_placement_check_not_found(client_and_db, seeded_checks):
    client, _ = client_and_db
    response = client.get("/placement-checks/nonexistent")
    assert response.status_code == 404


def test_placement_check_response_hides_reviewer_guidance(client_and_db, seeded_checks):
    client, _ = client_and_db
    response = client.get("/placement-checks/python")
    body_str = json.dumps(response.json())
    assert "Check for correct output" not in body_str
    assert "Use a loop, not sum()" not in body_str


# --- Worker endpoints ---

def test_client_only_account_cannot_start_attempt(client_and_db, seeded_checks):
    client, _ = client_and_db
    client_user = _create_user(client, "client-only@example.com", account_type="client")

    response = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(client_user),
    )
    assert response.status_code == 403
    assert "worker" in response.json()["detail"].lower()


def test_worker_can_start_attempt(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "worker@example.com", account_type="worker")

    response = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "started"
    assert body["variant_id"] in (1, 2)
    assert body["check"]["skill"] == "python"


def test_worker_cannot_start_two_in_progress(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "worker2@example.com", account_type="worker")

    first = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    assert first.status_code == 201

    second = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    assert second.status_code == 400
    assert "in-progress" in second.json()["detail"].lower()


def test_worker_can_submit_attempt(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "submitter@example.com", account_type="worker")

    start = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    attempt_id = start.json()["id"]

    response = client.post(
        f"/placement-attempts/{attempt_id}/submit",
        headers=_headers(worker),
        json={"submission": "Here is my implementation of sum_list using a loop."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None


def test_worker_cannot_submit_others_attempt(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "owner@example.com", account_type="worker")
    other = _create_user(client, "other@example.com", account_type="worker")

    start = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    attempt_id = start.json()["id"]

    response = client.post(
        f"/placement-attempts/{attempt_id}/submit",
        headers=_headers(other),
        json={"submission": "Hijacking someone else's attempt."},
    )
    assert response.status_code == 403


def test_start_attempt_nonexistent_check(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "nf@example.com", account_type="worker")

    response = client.post(
        "/placement-checks/nonexistent/attempts",
        headers=_headers(worker),
    )
    assert response.status_code == 404


def test_list_my_attempts(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "lister@example.com", account_type="worker")

    client.post("/placement-checks/python/attempts", headers=_headers(worker))

    response = client.get("/placement-attempts/me", headers=_headers(worker))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "started"


# --- Attempt limit & cooldown ---

def test_attempt_limit_enforced(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "limited@example.com", account_type="worker")

    for i in range(5):
        attempt = client.post(
            "/placement-checks/python/attempts",
            headers=_headers(worker),
        )
        assert attempt.status_code == 201
        client.post(
            f"/placement-attempts/{attempt.json()['id']}/submit",
            headers=_headers(worker),
            json={"submission": f"This is my attempt number {i+1} submission."},
        )

    response = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    assert response.status_code == 429


def test_variant_selection_alternates(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "switcher@example.com", account_type="worker")

    first = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    ).json()
    first_variant = first["variant_id"]

    client.post(
        f"/placement-attempts/{first['id']}/submit",
        headers=_headers(worker),
        json={"submission": "First attempt submission text here."},
    )

    second = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    ).json()
    second_variant = second["variant_id"]

    assert first_variant != second_variant


def test_explicit_variant_same_as_last_rejected(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "explicit@example.com", account_type="worker")

    first = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    ).json()
    first_variant = first["variant_id"]

    client.post(
        f"/placement-attempts/{first['id']}/submit",
        headers=_headers(worker),
        json={"submission": "Submitting first attempt for the variant test."},
    )

    response = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
        json={"variant_id": first_variant},
    )
    assert response.status_code == 400
    assert "different variant" in response.json()["detail"].lower()


# --- Admin review ---

def test_admin_can_pass_attempt(client_and_db, seeded_checks):
    client, _ = client_and_db
    admin = _create_user(client, "admin@example.com", account_type="both")
    _make_admin(client_and_db, admin)

    worker = _create_user(client, "skill-test@example.com", account_type="worker")
    start = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    attempt_id = start.json()["id"]

    client.post(
        f"/placement-attempts/{attempt_id}/submit",
        headers=_headers(worker),
        json={"submission": "Here is my implementation of sum_list using a loop."},
    )

    response = client.post(
        f"/admin/placement-attempts/{attempt_id}/review/pass",
        headers=_headers(admin),
        json={"feedback": "Good use of a for loop."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["feedback"] == "Good use of a for loop."

    profile = client.get("/profiles/me/worker", headers=_headers(worker))
    assert profile.status_code == 200
    assert "python" in profile.json()["verified_skills"]


def test_admin_can_mark_not_yet(client_and_db, seeded_checks):
    client, _ = client_and_db
    admin = _create_user(client, "admin2@example.com", account_type="both")
    _make_admin(client_and_db, admin)

    worker = _create_user(client, "notyet@example.com", account_type="worker")
    start = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    attempt_id = start.json()["id"]

    client.post(
        f"/placement-attempts/{attempt_id}/submit",
        headers=_headers(worker),
        json={"submission": "Here is my attempt for the not-yet test."},
    )

    response = client.post(
        f"/admin/placement-attempts/{attempt_id}/review/not-yet",
        headers=_headers(admin),
        json={"feedback": "Needs more error handling."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_yet"
    assert body["feedback"] == "Needs more error handling."

    profile = client.get("/profiles/me/worker", headers=_headers(worker))
    assert "python" not in profile.json()["verified_skills"]


def test_admin_review_requires_admin(client_and_db, seeded_checks):
    client, _ = client_and_db
    not_admin = _create_user(client, "notadmin@example.com", account_type="worker")
    worker = _create_user(client, "w2@example.com", account_type="worker")

    start = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    attempt_id = start.json()["id"]

    response = client.post(
        f"/admin/placement-attempts/{attempt_id}/review/pass",
        headers=_headers(not_admin),
    )
    assert response.status_code == 403


def test_admin_can_list_submitted_attempts(client_and_db, seeded_checks):
    client, _ = client_and_db
    admin = _create_user(client, "admin3@example.com", account_type="both")
    _make_admin(client_and_db, admin)

    worker = _create_user(client, "lister2@example.com", account_type="worker")
    start = client.post(
        "/placement-checks/python/attempts",
        headers=_headers(worker),
    )
    attempt_id = start.json()["id"]
    client.post(
        f"/placement-attempts/{attempt_id}/submit",
        headers=_headers(worker),
        json={"submission": "My submission for the admin listing test."},
    )

    response = client.get("/admin/placement-attempts", headers=_headers(admin))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "submitted"


def test_worker_cannot_directly_set_verified_skill(client_and_db, seeded_checks):
    client, _ = client_and_db
    worker = _create_user(client, "claimer@example.com", account_type="worker")

    client.put(
        "/profiles/me/worker",
        headers=_headers(worker),
        json={
            "skills": ["python"],
            "categories": [],
        },
    )

    profile = client.get("/profiles/me/worker", headers=_headers(worker))
    assert profile.status_code == 200
    assert "python" in profile.json()["skills"]
    assert "python" not in profile.json()["verified_skills"]
