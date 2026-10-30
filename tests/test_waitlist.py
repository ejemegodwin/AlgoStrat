def test_waitlist_accepts_and_normalizes_lead(client):
    response = client.post(
        "/waitlist",
        json={
            "email": "  Founder@Example.COM ",
            "audience": "business",
            "region": "europe",
            "consent": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "joined"


def test_waitlist_rejects_without_consent(client):
    response = client.post(
        "/waitlist",
        json={
            "email": "worker@example.com",
            "audience": "worker",
            "region": "africa",
            "consent": False,
        },
    )

    assert response.status_code == 422


def test_waitlist_rejects_duplicate_email(client):
    payload = {
        "email": "worker@example.com",
        "audience": "worker",
        "region": "africa",
        "consent": True,
    }

    assert client.post("/waitlist", json=payload).status_code == 201
    duplicate = client.post("/waitlist", json=payload)

    assert duplicate.status_code == 409
