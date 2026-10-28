def test_registration_normalizes_email_case(client):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Case Test User",
            "email": "Case.Test@Example.COM",
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == "case.test@example.com"


def test_duplicate_email_is_detected_regardless_of_case(client):
    first_response = client.post(
        "/auth/register",
        json={
            "full_name": "First User",
            "email": "shared@example.com",
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )
    second_response = client.post(
        "/auth/register",
        json={
            "full_name": "Second User",
            "email": "SHARED@example.com",
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "An account with this email already exists."
    )


def test_login_works_regardless_of_email_case(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Login Case User",
            "email": "logincase@example.com",
            "password": "SecurePass123!",
            "account_type": "both",
        },
    )
    assert register_response.status_code == 201

    for email_variant in ["logincase@example.com", "LoginCase@Example.com"]:
        login_response = client.post(
            "/auth/login",
            json={"email": email_variant, "password": "SecurePass123!"},
        )

        assert login_response.status_code == 200
        assert login_response.json()["access_token"]
