from app.core.security import create_access_token


def register(client, email):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Text Validation User",
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
        "title": "Build a company website",
        "description": "Create a professional website for a business.",
    }
    job_data.update(overrides)
    return client.post("/jobs", headers=headers, json=job_data)


def test_registration_rejects_whitespace_only_name(client):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "   ",
            "email": "whitespace-name@example.com",
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )

    assert response.status_code == 422


def test_registration_trims_full_name(client):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "  Padded Name  ",
            "email": "padded-name@example.com",
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )

    assert response.status_code == 201
    assert response.json()["full_name"] == "Padded Name"


def test_password_is_never_whitespace_stripped(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Spaced Password User",
            "email": "spaced-password@example.com",
            "password": "  SecurePass123!  ",
            "account_type": "both",
        },
    )
    assert register_response.status_code == 201

    # The exact password, spaces included, authenticates...
    exact_login = client.post(
        "/auth/login",
        json={
            "email": "spaced-password@example.com",
            "password": "  SecurePass123!  ",
        },
    )
    assert exact_login.status_code == 200

    # ...and the trimmed variant must NOT authenticate.
    trimmed_login = client.post(
        "/auth/login",
        json={
            "email": "spaced-password@example.com",
            "password": "SecurePass123!",
        },
    )
    assert trimmed_login.status_code == 401


def test_create_job_rejects_whitespace_only_title(client):
    headers = register(client, "ws-title@example.com")

    response = create_job(client, headers, title="     ")

    assert response.status_code == 422


def test_create_job_trims_title_and_description(client):
    headers = register(client, "trim-job@example.com")

    response = create_job(
        client,
        headers,
        title="  Build a website  ",
        description="  Create a professional business website.  ",
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Build a website"
    assert response.json()["description"] == (
        "Create a professional business website."
    )


def test_create_job_title_length_is_checked_after_trimming(client):
    headers = register(client, "trim-length@example.com")

    too_short = create_job(client, headers, title="  ab  ")
    assert too_short.status_code == 422

    exactly_three = create_job(client, headers, title="  abc  ")
    assert exactly_three.status_code == 201
    assert exactly_three.json()["title"] == "abc"


def test_create_job_rejects_whitespace_only_description(client):
    headers = register(client, "ws-description@example.com")

    response = create_job(client, headers, description="          ")

    assert response.status_code == 422


def test_whitespace_only_category_and_location_become_null(client):
    headers = register(client, "ws-optional@example.com")

    response = create_job(client, headers, category="   ", location="\t\n ")

    assert response.status_code == 201
    assert response.json()["category"] is None
    assert response.json()["location"] is None


def test_update_job_trims_text_fields(client):
    headers = register(client, "update-trim@example.com")
    create_response = create_job(client, headers)
    job_id = create_response.json()["id"]

    response = client.patch(
        f"/jobs/{job_id}",
        headers=headers,
        json={"title": "  Updated title  ", "location": "  Lagos, Nigeria "},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated title"
    assert response.json()["location"] == "Lagos, Nigeria"


def test_apply_rejects_whitespace_only_cover_letter(client):
    owner_headers = register(client, "ws-cover-owner@example.com")
    job_id = create_job(client, owner_headers).json()["id"]
    worker_headers = register(client, "ws-cover-worker@example.com")

    response = client.post(
        f"/jobs/{job_id}/applications",
        headers=worker_headers,
        json={"cover_letter": " " * 50},
    )

    assert response.status_code == 422


def test_apply_trims_cover_letter(client):
    owner_headers = register(client, "trim-cover-owner@example.com")
    job_id = create_job(client, owner_headers).json()["id"]
    worker_headers = register(client, "trim-cover-worker@example.com")

    response = client.post(
        f"/jobs/{job_id}/applications",
        headers=worker_headers,
        json={
            "cover_letter": (
                "   I have the skills and experience for this project.   "
            ),
        },
    )

    assert response.status_code == 201
    assert response.json()["cover_letter"] == (
        "I have the skills and experience for this project."
    )
