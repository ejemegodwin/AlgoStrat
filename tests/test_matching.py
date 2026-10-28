import pytest

from app.core.security import create_access_token


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


def create_job(client, owner_headers, category=None, budget=None, currency=None):
    payload = {
        "title": "Build a company website",
        "description": "Create a professional website for a business.",
    }
    if category is not None:
        payload["category"] = category
    if budget is not None:
        payload["budget"] = budget
    if currency is not None:
        payload["currency"] = currency

    response = client.post("/jobs", headers=owner_headers, json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def set_profile(client, headers, **kwargs):
    response = client.put("/profiles/me/worker", headers=headers, json=kwargs)
    assert response.status_code == 200


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


def recommended(client, headers, **params):
    response = client.get("/jobs/recommended", headers=headers, params=params)
    assert response.status_code == 200
    return response.json()


def hire_and_get_contract(client, owner_headers, worker_headers, job_kwargs=None):
    """Full hire; returns (job_id, contract_id)."""
    job_id = create_job(client, owner_headers, **(job_kwargs or {}))
    application_id = apply(client, job_id, worker_headers)
    decide = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers=owner_headers,
        json={"status": "accepted"},
    )
    assert decide.status_code == 200
    contract_id = client.get("/contracts", headers=owner_headers).json()[0]["id"]
    return job_id, contract_id


def add_reviewed_milestone(
    client, contract_id, owner_headers, worker_headers, decision
):
    """Add a milestone, submit it, and review it as requested."""
    milestone = client.post(
        f"/contracts/{contract_id}/milestones",
        headers=owner_headers,
        json={"title": "Reviewed milestone"},
    )
    assert milestone.status_code == 201
    milestone_id = milestone.json()["id"]

    submit = client.post(
        f"/milestones/{milestone_id}/submit",
        headers=worker_headers,
        json={"note": "Here is the completed work."},
    )
    assert submit.status_code == 200

    payload = {"decision": decision}
    if decision == "request_changes":
        payload["note"] = "Please revise and resubmit."
    review = client.post(
        f"/milestones/{milestone_id}/review",
        headers=owner_headers,
        json=payload,
    )
    assert review.status_code == 200


def complete_one_contract(client, owner_headers, worker_headers):
    """Give the worker one completed contract on their record."""
    _, contract_id = hire_and_get_contract(client, owner_headers, worker_headers)
    add_reviewed_milestone(
        client, contract_id, owner_headers, worker_headers, "approve"
    )
    complete = client.post(
        f"/contracts/{contract_id}/complete", headers=owner_headers
    )
    assert complete.status_code == 200


# --- Jobs recommended for the worker -------------------------------------


def test_category_match_ranks_above_non_match(client):
    _, owner_headers = register(client, "Owner", "cat-owner@example.com")
    _, worker_headers = register(client, "Worker", "cat-worker@example.com")
    design_job = create_job(client, owner_headers, category="Design")
    plumbing_job = create_job(client, owner_headers, category="Plumbing")
    set_profile(client, worker_headers, categories=["design"])

    results = recommended(client, worker_headers)

    assert [r["job"]["id"] for r in results] == [design_job, plumbing_job]
    match = results[0]
    assert match["factors"]["category"]["score"] == 1.0
    assert "matches your declared categories" in match["factors"]["category"]["reason"]
    outside = results[1]
    assert outside["factors"]["category"]["score"] == 0.0
    assert "outside your declared categories" in outside["factors"]["category"]["reason"]


def test_recommendations_exclude_closed_and_own_jobs(client):
    _, owner_headers = register(client, "Owner", "excl-owner@example.com")
    _, worker_headers = register(client, "Worker", "excl-worker@example.com")
    closed_job = create_job(client, owner_headers)
    close = client.patch(f"/jobs/{closed_job}/close", headers=owner_headers)
    assert close.status_code == 200
    own_job = create_job(client, worker_headers)

    results = recommended(client, worker_headers)
    job_ids = [r["job"]["id"] for r in results]
    assert closed_job not in job_ids
    assert own_job not in job_ids


def test_newcomer_gets_neutral_reliability_and_empty_track_record(client):
    _, owner_headers = register(client, "Owner", "new-owner@example.com")
    _, worker_headers = register(client, "Worker", "new-worker@example.com")
    create_job(client, owner_headers)

    results = recommended(client, worker_headers)

    factors = results[0]["factors"]
    assert factors["reliability"]["score"] == 0.5
    assert "neutral" in factors["reliability"]["reason"]
    assert factors["track_record"]["score"] == 0.0
    assert "No completed contracts" in factors["track_record"]["reason"]
    # With an empty profile, category cannot match and budget is open.
    assert factors["category"]["score"] == 0.0
    assert factors["budget"]["score"] == 1.0


def test_budget_factor_cases(client):
    _, owner_headers = register(client, "Owner", "budget-owner@example.com")
    _, worker_headers = register(client, "Worker", "budget-worker@example.com")
    rich_job = create_job(client, owner_headers, budget="1000.00", currency="USD")
    poor_job = create_job(client, owner_headers, budget="100.00", currency="USD")
    mystery_job = create_job(client, owner_headers)
    set_profile(client, worker_headers, min_budget="500.00")

    results = {r["job"]["id"]: r for r in recommended(client, worker_headers)}

    assert results[rich_job]["factors"]["budget"]["score"] == 1.0
    assert "meets the" in results[rich_job]["factors"]["budget"]["reason"]
    assert results[poor_job]["factors"]["budget"]["score"] == 0.0
    assert "below the" in results[poor_job]["factors"]["budget"]["reason"]
    assert results[mystery_job]["factors"]["budget"]["score"] == 0.5
    assert "unknown" in results[mystery_job]["factors"]["budget"]["reason"]


def test_track_record_and_reliability_grow_with_verified_history(client):
    _, owner_headers = register(client, "Owner", "hist-owner@example.com")
    _, worker_headers = register(client, "Worker", "hist-worker@example.com")
    _, other_owner_headers = register(client, "Owner2", "hist-owner-2@example.com")

    # One completed contract with an approval on the worker's record,
    # plus one changes-requested review on a second live contract.
    complete_one_contract(client, owner_headers, worker_headers)
    _, live_contract_id = hire_and_get_contract(
        client, other_owner_headers, worker_headers
    )
    add_reviewed_milestone(
        client, live_contract_id, other_owner_headers, worker_headers,
        "request_changes",
    )

    create_job(client, other_owner_headers, category="Design", budget="1000.00", currency="USD")
    set_profile(client, worker_headers, categories=["design"], min_budget="500.00")

    results = recommended(client, worker_headers)
    match = next(r for r in results if r["job"]["category"] == "Design")

    # 1 completed contract of 3 for full credit.
    assert match["factors"]["track_record"]["score"] == pytest.approx(1 / 3)
    # 1 approval + 1 changes-requested = a 50% approval share.
    assert match["factors"]["reliability"]["score"] == 0.5
    assert "1 of 2 milestone reviews were approvals" in match["factors"]["reliability"]["reason"]

    # Full weighted total: 0.40 + 0.20 + 0.25/3 + 0.15*0.5 = 0.758
    assert match["score"] == pytest.approx(0.758, abs=0.001)


def test_recommendations_pagination_and_auth(client):
    _, owner_headers = register(client, "Owner", "page-owner@example.com")
    _, worker_headers = register(client, "Worker", "page-worker@example.com")
    for _ in range(3):
        create_job(client, owner_headers)

    page = recommended(client, worker_headers, limit=2, offset=0)
    assert len(page) == 2
    rest = recommended(client, worker_headers, limit=2, offset=2)
    assert len(rest) == 1
    assert {r["job"]["id"] for r in page}.isdisjoint(
        {r["job"]["id"] for r in rest}
    )

    assert client.get("/jobs/recommended", headers=worker_headers, params={"limit": 0}).status_code == 422
    assert client.get("/jobs/recommended", headers=worker_headers, params={"limit": 101}).status_code == 422
    assert client.get("/jobs/recommended", headers=worker_headers, params={"offset": -1}).status_code == 422
    assert client.get("/jobs/recommended").status_code == 401


# --- Applicants ranked for the job owner -----------------------------------


def test_owner_sees_applicants_ranked_by_the_same_score(client):
    _, owner_headers = register(client, "Owner", "rank-owner@example.com")
    _, strong_headers = register(client, "Strong", "rank-strong@example.com")
    _, plain_headers = register(client, "Plain", "rank-plain@example.com")

    job_id = create_job(client, owner_headers, category="Design")
    strong_application = apply(client, job_id, strong_headers)
    plain_application = apply(client, job_id, plain_headers)
    set_profile(client, strong_headers, categories=["design"])

    response = client.get(
        f"/jobs/{job_id}/applicants/ranked", headers=owner_headers
    )

    assert response.status_code == 200
    ranked = response.json()
    assert [r["application"]["id"] for r in ranked] == [
        strong_application,
        plain_application,
    ]
    assert ranked[0]["worker_name"] == "Strong"
    assert ranked[0]["score"] > ranked[1]["score"]

    # Transparency rule: the owner and the worker see the SAME score,
    # computed from the same factors and weights.
    worker_view = recommended(client, strong_headers)
    own = next(r for r in worker_view if r["job"]["id"] == job_id)
    assert ranked[0]["score"] == own["score"]


def test_ranked_applicants_are_pending_only(client):
    _, owner_headers = register(client, "Owner", "pool-owner@example.com")
    _, stayer_headers = register(client, "Stayer", "pool-stayer@example.com")
    _, leaver_headers = register(client, "Leaver", "pool-leaver@example.com")

    job_id = create_job(client, owner_headers)
    stayer_application = apply(client, job_id, stayer_headers)
    leaver_application = apply(client, job_id, leaver_headers)

    withdraw = client.patch(
        f"/applications/{leaver_application}/withdraw", headers=leaver_headers
    )
    assert withdraw.status_code == 200

    ranked = client.get(
        f"/jobs/{job_id}/applicants/ranked", headers=owner_headers
    ).json()
    assert [r["application"]["id"] for r in ranked] == [stayer_application]

    # After the hire, no decision remains: the ranked pool is empty.
    decide = client.patch(
        f"/jobs/{job_id}/applications/{stayer_application}",
        headers=owner_headers,
        json={"status": "accepted"},
    )
    assert decide.status_code == 200
    assert client.get(
        f"/jobs/{job_id}/applicants/ranked", headers=owner_headers
    ).json() == []


def test_ranked_applicants_authorization(client):
    _, owner_headers = register(client, "Owner", "ra-authz-owner@example.com")
    _, worker_headers = register(client, "Worker", "ra-authz-worker@example.com")
    _, outsider_headers = register(client, "Outsider", "ra-authz-outsider@example.com")

    job_id = create_job(client, owner_headers)
    apply(client, job_id, worker_headers)

    assert client.get(
        f"/jobs/{job_id}/applicants/ranked", headers=worker_headers
    ).status_code == 403
    assert client.get(
        f"/jobs/{job_id}/applicants/ranked", headers=outsider_headers
    ).status_code == 403
    assert client.get(f"/jobs/{job_id}/applicants/ranked").status_code == 401
    assert client.get(
        "/jobs/9999/applicants/ranked", headers=owner_headers
    ).status_code == 404
