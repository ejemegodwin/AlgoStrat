"""Worker profile details + the self-reported vs verified skill split."""

from app.core.security import create_access_token
from app.models import ProfileTag


def create_worker_headers(client, email, name="Profile Test Worker"):
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
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}, user_id


def test_profile_details_round_trip(client):
    headers, _ = create_worker_headers(client, "pd-round@example.com")

    saved = client.put(
        "/profiles/me/worker",
        headers=headers,
        json={
            "availability": "available",
            "headline": "Spreadsheet cleanup specialist",
            "bio": "Two years of data cleaning for small shops.",
            "country": "Nigeria",
            "timezone": "Africa/Lagos",
            "skills": ["Excel", "Data Cleaning"],
            "categories": ["Data Entry"],
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["headline"] == "Spreadsheet cleanup specialist"
    assert body["bio"].startswith("Two years")
    assert body["country"] == "Nigeria"
    assert body["timezone"] == "Africa/Lagos"

    fetched = client.get("/profiles/me/worker", headers=headers).json()
    assert fetched == body


def test_detail_fields_are_optional(client):
    headers, _ = create_worker_headers(client, "pd-min@example.com")

    saved = client.put(
        "/profiles/me/worker",
        headers=headers,
        json={"skills": ["Python"]},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["headline"] is None
    assert body["bio"] is None
    assert body["country"] is None
    assert body["timezone"] is None


def test_skills_are_self_reported_never_verified_via_api(client):
    headers, _ = create_worker_headers(client, "pd-selfrep@example.com")

    saved = client.put(
        "/profiles/me/worker",
        headers=headers,
        json={
            "skills": ["Excel"],
            # An attempt to smuggle verification in — must be ignored.
            "verified_skills": ["Excel"],
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["skills"] == ["excel"]
    assert body["verified_skills"] == []


def test_verified_skill_survives_profile_update(client_and_db):
    client, session_factory = client_and_db
    headers, user_id = create_worker_headers(client, "pd-keep@example.com")

    client.put(
        "/profiles/me/worker",
        headers=headers,
        json={"skills": ["excel", "python"]},
    )
    # The platform (e.g. a future placement check) verifies one skill.
    db = session_factory()
    db.query(ProfileTag).filter_by(
        user_id=user_id, kind="skill", value="excel"
    ).update({"verified": True})
    db.commit()
    db.close()

    # Worker edits their profile, keeping excel, dropping python.
    updated = client.put(
        "/profiles/me/worker",
        headers=headers,
        json={"headline": "Data cleanup", "skills": ["excel", "sql"]},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["verified_skills"] == ["excel"]
    assert body["skills"] == ["sql"]  # self-reported list excludes verified


def test_dropping_a_verified_skill_drops_its_verification(client_and_db):
    client, session_factory = client_and_db
    headers, user_id = create_worker_headers(client, "pd-drop@example.com")

    client.put(
        "/profiles/me/worker", headers=headers, json={"skills": ["excel"]}
    )
    db = session_factory()
    db.query(ProfileTag).filter_by(
        user_id=user_id, kind="skill", value="excel"
    ).update({"verified": True})
    db.commit()
    db.close()

    updated = client.put(
        "/profiles/me/worker", headers=headers, json={"skills": ["sql"]}
    )
    assert updated.status_code == 200
    assert updated.json()["verified_skills"] == []


def test_detail_field_lengths_are_validated(client):
    headers, _ = create_worker_headers(client, "pd-valid@example.com")

    for field, value in [
        ("headline", "x" * 151),
        ("country", "x" * 101),
        ("timezone", "x" * 51),
    ]:
        response = client.put(
            "/profiles/me/worker", headers=headers, json={field: value}
        )
        assert response.status_code == 422, field
