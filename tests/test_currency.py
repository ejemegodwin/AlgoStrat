from app.core.security import create_access_token


def create_user_headers(client, email="currency-owner@example.com"):
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Currency Test User",
            "email": email,
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def create_job(client, headers, **overrides):
    job_data = {
        "title": "Build a company website",
        "description": "Create a professional website for a business.",
        "budget": "500.00",
    }
    job_data.update(overrides)

    response = client.post("/jobs", headers=headers, json=job_data)
    assert response.status_code == 201
    return response.json()


def test_create_job_normalizes_lowercase_currency(client):
    headers = create_user_headers(client)

    job = create_job(client, headers, currency="usd")

    assert job["currency"] == "USD"


def test_create_job_trims_and_normalizes_currency(client):
    headers = create_user_headers(client)

    job = create_job(client, headers, currency="  ngn  ")

    assert job["currency"] == "NGN"


def test_create_job_defaults_to_usd(client):
    headers = create_user_headers(client)

    job = create_job(client, headers)

    assert job["currency"] == "USD"


def test_create_job_rejects_malformed_currency_codes(client):
    headers = create_user_headers(client)

    for bad_currency in ["us1", "US", "USDD", "U D", ""]:
        response = client.post(
            "/jobs",
            headers=headers,
            json={
                "title": "Build a company website",
                "description": "Create a professional website for a business.",
                "currency": bad_currency,
            },
        )

        assert response.status_code == 422, f"expected 422 for {bad_currency!r}"


def test_create_job_rejects_unsupported_currency_code(client):
    headers = create_user_headers(client)

    response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Build a company website",
            "description": "Create a professional website for a business.",
            "currency": "XXX",
        },
    )

    assert response.status_code == 422


def test_create_job_rejects_non_ascii_currency_code(client):
    headers = create_user_headers(client)

    response = client.post(
        "/jobs",
        headers=headers,
        json={
            "title": "Build a company website",
            "description": "Create a professional website for a business.",
            "currency": "ÄÖÜ",
        },
    )

    assert response.status_code == 422


def test_update_job_normalizes_currency(client):
    headers = create_user_headers(client)
    job = create_job(client, headers, currency="USD")

    response = client.patch(
        f"/jobs/{job['id']}",
        headers=headers,
        json={"currency": "  gbp "},
    )

    assert response.status_code == 200
    assert response.json()["currency"] == "GBP"


def test_update_job_rejects_invalid_currency_and_keeps_stored_value(client):
    headers = create_user_headers(client)
    job = create_job(client, headers, currency="EUR")

    for bad_currency in ["xx", "x1y", "ZZZ"]:
        response = client.patch(
            f"/jobs/{job['id']}",
            headers=headers,
            json={"currency": bad_currency},
        )
        assert response.status_code == 422, f"expected 422 for {bad_currency!r}"

    unchanged = client.get(f"/jobs/{job['id']}")
    assert unchanged.status_code == 200
    assert unchanged.json()["currency"] == "EUR"


def test_update_job_rejects_null_currency(client):
    headers = create_user_headers(client)
    job = create_job(client, headers, currency="USD")

    response = client.patch(
        f"/jobs/{job['id']}",
        headers=headers,
        json={"currency": None},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "currency cannot be null."
