def register(client, email):
    return client.post(
        "/auth/register",
        json={
            "full_name": "Rate Limit User",
            "email": email,
            "password": "SecurePass123!",
        },
    )


def test_login_is_rate_limited_after_repeated_failures(client):
    register_response = register(client, "login-limited@example.com")
    assert register_response.status_code == 201

    for attempt in range(5):
        response = client.post(
            "/auth/login",
            json={
                "email": "login-limited@example.com",
                "password": "WrongPass123!",
            },
        )
        assert response.status_code == 401, f"attempt {attempt + 1}"

    # The sixth attempt is rejected before any password check.
    response = client.post(
        "/auth/login",
        json={
            "email": "login-limited@example.com",
            "password": "WrongPass123!",
        },
    )
    assert response.status_code == 429
    assert response.json()["detail"] == (
        "Too many attempts. Please try again later."
    )

    # Even the correct password is blocked while limited.
    response = client.post(
        "/auth/login",
        json={
            "email": "login-limited@example.com",
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 429


def test_login_attempts_with_unknown_email_count_toward_limit(client):
    for attempt in range(5):
        response = client.post(
            "/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "SecurePass123!",
            },
        )
        assert response.status_code == 401, f"attempt {attempt + 1}"

    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "SecurePass123!"},
    )
    assert response.status_code == 429


def test_registration_is_rate_limited_after_repeated_signups(client):
    for i in range(10):
        response = register(client, f"signup-limited-{i}@example.com")
        assert response.status_code == 201, f"signup {i + 1}"

    response = register(client, "signup-limited-11@example.com")
    assert response.status_code == 429
    assert response.json()["detail"] == (
        "Too many attempts. Please try again later."
    )
