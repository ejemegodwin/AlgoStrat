from app.core.security import create_access_token


def register(client, full_name, email):
    response = client.post(
        "/auth/register",
        json={
            "full_name": full_name,
            "email": email,
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    return user_id, {"Authorization": f"Bearer {create_access_token(user_id)}"}


def upsert_profile(client, headers, **kwargs):
    return client.put("/profiles/me/worker", headers=headers, json=kwargs)


def get_profile(client, headers):
    response = client.get("/profiles/me/worker", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_profile_defaults_when_never_created(client):
    _, headers = register(client, "Worker", "default-profile@example.com")

    profile = get_profile(client, headers)
    assert profile == {
        "availability": "available",
        "min_budget": None,
        "skills": [],
        "categories": [],
    }


def test_upsert_creates_and_returns_the_profile(client):
    _, headers = register(client, "Worker", "create-profile@example.com")

    response = upsert_profile(
        client,
        headers,
        availability="busy",
        min_budget="500.00",
        skills=["Python", "FastAPI"],
        categories=["Design", "Software"],
    )

    assert response.status_code == 200
    profile = response.json()
    assert profile["availability"] == "busy"
    assert str(profile["min_budget"]) in ("500.00", "500.0", "500")
    assert profile["skills"] == ["python", "fastapi"]
    # Tags are lowercased so matching compares like with like.
    assert profile["categories"] == ["design", "software"]


def test_tags_are_trimmed_lowercased_and_deduplicated(client):
    _, headers = register(client, "Worker", "normalize-profile@example.com")

    response = upsert_profile(
        client,
        headers,
        skills=["  Python  ", "PYTHON", "python ", "SQL"],
        categories=["  Design "],
    )

    assert response.status_code == 200
    assert response.json()["skills"] == ["python", "sql"]
    assert response.json()["categories"] == ["design"]


def test_put_replaces_the_tag_lists_entirely(client):
    _, headers = register(client, "Worker", "replace-profile@example.com")

    upsert_profile(client, headers, skills=["python"], categories=["design"])
    upsert_profile(client, headers, skills=["writing"], categories=["legal"])

    profile = get_profile(client, headers)
    assert profile["skills"] == ["writing"]
    assert profile["categories"] == ["legal"]


def test_profile_validation(client):
    _, headers = register(client, "Worker", "validate-profile@example.com")

    # Availability is constrained.
    assert upsert_profile(client, headers, availability="sleepy").status_code == 422
    # Minimum budget must be positive when present.
    assert upsert_profile(client, headers, min_budget="0").status_code == 422
    assert upsert_profile(client, headers, min_budget="-10").status_code == 422
    # Tag caps: at most 10 skills and 5 categories.
    assert upsert_profile(
        client, headers, skills=[f"skill-{i}" for i in range(11)]
    ).status_code == 422
    assert upsert_profile(
        client, headers, categories=[f"category-{i}" for i in range(6)]
    ).status_code == 422


def test_profiles_require_authentication(client):
    assert client.get("/profiles/me/worker").status_code == 401
    assert client.put("/profiles/me/worker", json={}).status_code == 401
