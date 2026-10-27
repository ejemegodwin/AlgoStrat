from app.core.security import create_access_token


def create_job(client, headers, title, **overrides):
    job_data = {
        "title": title,
        "description": "A professional engagement with clear deliverables.",
    }
    job_data.update(overrides)
    response = client.post("/jobs", headers=headers, json=job_data)
    assert response.status_code == 201
    return response.json()["id"]


def test_like_wildcards_in_keyword_match_literally(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Wildcard Search User",
            "email": "wildcard-search@example.com",
            "password": "SecurePass123!",
        },
    )
    user_id = register_response.json()["id"]
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}

    percent_job_id = create_job(
        client, headers, "Design a 100% unique company logo"
    )
    plain_job_id = create_job(
        client, headers, "Design a company letterhead"
    )

    # A literal percent sign must only match the job containing one.
    response = client.get("/jobs?keyword=100%25")  # URL-encoded "100%"
    assert response.status_code == 200
    ids = [job["id"] for job in response.json()]
    assert ids == [percent_job_id]

    # An unescaped "%" would match every job; escaped, it matches only
    # titles/descriptions containing a literal percent character.
    response = client.get("/jobs?keyword=%25")  # URL-encoded "%"
    assert response.status_code == 200
    ids = [job["id"] for job in response.json()]
    assert ids == [percent_job_id]

    # Sanity check: a normal keyword still performs substring matching.
    response = client.get("/jobs?keyword=company")
    assert response.status_code == 200
    ids = {job["id"] for job in response.json()}
    assert ids == {percent_job_id, plain_job_id}


def test_like_underscore_in_keyword_matches_literally(client):
    register_response = client.post(
        "/auth/register",
        json={
            "full_name": "Underscore Search User",
            "email": "underscore-search@example.com",
            "password": "SecurePass123!",
        },
    )
    user_id = register_response.json()["id"]
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}

    underscore_job_id = create_job(
        client, headers, "Maintain legacy_system integration"
    )
    create_job(client, headers, "Maintain legacyXsystem integration")

    # "_" as a wildcard would match both; escaped, only the real one.
    response = client.get("/jobs?keyword=legacy_system")
    assert response.status_code == 200
    ids = [job["id"] for job in response.json()]
    assert ids == [underscore_job_id]
