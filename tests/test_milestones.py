from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

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


def hire(client, owner_headers, worker_headers, budget=None, currency=None):
    """Run a full hire and return the new contract's id."""
    payload = {
        "title": "Build a company website",
        "description": "Create a professional website for a business.",
    }
    if budget is not None:
        payload["budget"] = budget
    if currency is not None:
        payload["currency"] = currency

    job_response = client.post("/jobs", headers=owner_headers, json=payload)
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    apply_response = client.post(
        f"/jobs/{job_id}/applications",
        headers=worker_headers,
        json={
            "cover_letter": (
                "I have the skills and experience to complete this project."
            ),
        },
    )
    assert apply_response.status_code == 201
    application_id = apply_response.json()["id"]

    decide_response = client.patch(
        f"/jobs/{job_id}/applications/{application_id}",
        headers=owner_headers,
        json={"status": "accepted"},
    )
    assert decide_response.status_code == 200

    contracts = client.get("/contracts", headers=owner_headers).json()
    return contracts[0]["id"]


def add_milestone(client, contract_id, headers, title="Design mockups", **kwargs):
    payload = {"title": title}
    payload.update(kwargs)
    return client.post(
        f"/contracts/{contract_id}/milestones",
        headers=headers,
        json=payload,
    )


def get_detail(client, contract_id, headers):
    response = client.get(f"/contracts/{contract_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


def get_events(client, contract_id, headers):
    response = client.get(
        f"/contracts/{contract_id}/events", headers=headers
    )
    assert response.status_code == 200
    return response.json()


def submit(client, milestone_id, headers, note="Here is the completed work."):
    return client.post(
        f"/milestones/{milestone_id}/submit",
        headers=headers,
        json={"note": note},
    )


def review(client, milestone_id, headers, decision, note=None):
    payload = {"decision": decision}
    if note is not None:
        payload["note"] = note
    return client.post(
        f"/milestones/{milestone_id}/review",
        headers=headers,
        json=payload,
    )


def setup_contract(client, email_prefix, budget=None, currency=None):
    """Register an owner and a worker, hire, and return everything."""
    owner_id, owner_headers = register(
        client, "Owner", f"{email_prefix}-owner@example.com"
    )
    worker_id, worker_headers = register(
        client, "Worker", f"{email_prefix}-worker@example.com"
    )
    contract_id = hire(
        client, owner_headers, worker_headers, budget, currency
    )
    return owner_id, owner_headers, worker_id, worker_headers, contract_id


# --- Adding milestones -------------------------------------------------


def test_client_can_add_a_milestone(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "add")

    response = add_milestone(
        client,
        contract_id,
        owner_headers,
        amount="250.00",
        description="  First draft of the homepage.  ",
    )

    assert response.status_code == 201
    milestone = response.json()
    assert milestone["title"] == "Design mockups"
    # Whitespace is stripped; whitespace-only would have become null.
    assert milestone["description"] == "First draft of the homepage."
    assert milestone["status"] == "pending"
    assert milestone["position"] == 1
    assert milestone["submission_note"] is None

    event_types = [e["event_type"] for e in get_events(client, contract_id, owner_headers)]
    assert event_types == ["contract_created", "milestone_added"]


def test_milestone_positions_increment_automatically(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "positions")

    first = add_milestone(client, contract_id, owner_headers, title="First milestone")
    second = add_milestone(client, contract_id, owner_headers, title="Second milestone")
    explicit = add_milestone(
        client, contract_id, owner_headers, title="Jumped milestone", position=10
    )
    following = add_milestone(client, contract_id, owner_headers, title="After jump")

    assert first.status_code == second.status_code == 201
    assert explicit.status_code == following.status_code == 201
    assert second.json()["position"] == 2
    assert explicit.json()["position"] == 10
    assert following.json()["position"] == 11

    milestones = get_detail(client, contract_id, owner_headers)["milestones"]
    assert [m["position"] for m in milestones] == [1, 2, 10, 11]


def test_worker_and_outsider_cannot_add_milestones(client):
    _, _, _, worker_headers, contract_id = setup_contract(client, "add-authz")
    _, outsider_headers = register(
        client, "Outsider", "add-authz-outsider@example.com"
    )

    assert add_milestone(client, contract_id, worker_headers).status_code == 403
    assert add_milestone(client, contract_id, outsider_headers).status_code == 403


def test_cannot_add_a_milestone_to_an_inactive_contract(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "add-inactive")

    cancel = client.post(
        f"/contracts/{contract_id}/cancel", headers=owner_headers
    )
    assert cancel.status_code == 200

    response = add_milestone(client, contract_id, owner_headers)
    assert response.status_code == 400


def test_milestone_amounts_cannot_exceed_the_agreed_amount(client):
    _, owner_headers, _, _, contract_id = setup_contract(
        client, "budget", budget="1000.00", currency="USD"
    )

    assert add_milestone(client, contract_id, owner_headers, title="Milestone 1", amount="600").status_code == 201
    overflow = add_milestone(client, contract_id, owner_headers, title="Milestone 2", amount="500")
    assert overflow.status_code == 400
    assert "agreed amount" in overflow.json()["detail"]
    # 600 + 400 lands exactly on the budget: allowed.
    assert add_milestone(client, contract_id, owner_headers, title="Milestone 3", amount="400").status_code == 201
    # Amountless milestones never count against the budget.
    assert add_milestone(client, contract_id, owner_headers, title="Milestone 4").status_code == 201


def test_milestone_amounts_are_unrestricted_without_an_agreed_amount(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "no-budget")

    response = add_milestone(client, contract_id, owner_headers, amount="999999.99")
    assert response.status_code == 201


# --- Editing and deleting milestones ------------------------------------


def test_client_can_edit_a_pending_milestone(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "edit")
    milestone_id = add_milestone(
        client, contract_id, owner_headers, amount="100"
    ).json()["id"]

    response = client.patch(
        f"/milestones/{milestone_id}",
        headers=owner_headers,
        json={
            "title": "  Revised design mockups  ",
            "due_date": "2027-01-15T00:00:00Z",
            "amount": None,  # explicit null clears the amount
        },
    )

    assert response.status_code == 200
    milestone = response.json()
    assert milestone["title"] == "Revised design mockups"
    assert milestone["due_date"].startswith("2027-01-15")
    assert milestone["amount"] is None


def test_editing_a_milestone_respects_the_budget_rule(client):
    _, owner_headers, _, _, contract_id = setup_contract(
        client, "edit-budget", budget="1000", currency="USD"
    )
    add_milestone(client, contract_id, owner_headers, title="Milestone 1", amount="600")
    second_id = add_milestone(
        client, contract_id, owner_headers, title="Milestone 2", amount="300"
    ).json()["id"]

    overflow = client.patch(
        f"/milestones/{second_id}",
        headers=owner_headers,
        json={"amount": "401"},
    )
    assert overflow.status_code == 400

    fits = client.patch(
        f"/milestones/{second_id}",
        headers=owner_headers,
        json={"amount": "400"},
    )
    assert fits.status_code == 200


def test_cannot_edit_or_delete_a_submitted_milestone(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "edit-submitted"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]
    assert submit(client, milestone_id, worker_headers).status_code == 200

    edit = client.patch(
        f"/milestones/{milestone_id}",
        headers=owner_headers,
        json={"title": "Too late to change"},
    )
    assert edit.status_code == 400

    delete = client.delete(f"/milestones/{milestone_id}", headers=owner_headers)
    assert delete.status_code == 400


def test_worker_cannot_edit_or_delete_milestones(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "edit-authz"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]

    edit = client.patch(
        f"/milestones/{milestone_id}",
        headers=worker_headers,
        json={"title": "Worker meddling"},
    )
    assert edit.status_code == 403

    delete = client.delete(f"/milestones/{milestone_id}", headers=worker_headers)
    assert delete.status_code == 403


def test_deleting_a_milestone_preserves_the_audit_trail(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "delete")
    milestone_id = add_milestone(
        client, contract_id, owner_headers, title="Doomed milestone"
    ).json()["id"]

    delete = client.delete(f"/milestones/{milestone_id}", headers=owner_headers)
    assert delete.status_code == 204

    assert get_detail(client, contract_id, owner_headers)["milestones"] == []

    events = get_events(client, contract_id, owner_headers)
    assert [e["event_type"] for e in events] == [
        "contract_created",
        "milestone_added",
        "milestone_removed",
    ]
    # The trail survives: earlier events are unlinked, not destroyed, and
    # the removal note carries the deleted milestone's title.
    assert all(e["milestone_id"] is None for e in events)
    assert events[-1]["note"] == "Doomed milestone"


# --- Submit and review ---------------------------------------------------


def test_worker_can_submit_a_pending_milestone(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "submit"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]

    response = submit(client, milestone_id, worker_headers)

    assert response.status_code == 200
    milestone = response.json()
    assert milestone["status"] == "submitted"
    assert milestone["submission_note"] == "Here is the completed work."
    assert milestone["submitted_at"] is not None

    events = get_events(client, contract_id, owner_headers)
    last = events[-1]
    assert last["event_type"] == "milestone_submitted"
    assert last["note"] == "Here is the completed work."
    assert last["milestone_id"] == milestone_id


def test_only_the_worker_can_submit(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "submit-authz")
    _, outsider_headers = register(
        client, "Outsider", "submit-authz-outsider@example.com"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]

    assert submit(client, milestone_id, owner_headers).status_code == 403
    assert submit(client, milestone_id, outsider_headers).status_code == 403


def test_cannot_resubmit_an_already_submitted_milestone(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "resubmit"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]
    assert submit(client, milestone_id, worker_headers).status_code == 200

    assert submit(client, milestone_id, worker_headers).status_code == 400


def test_client_can_approve_a_submitted_milestone_and_it_is_terminal(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "approve"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]
    assert submit(client, milestone_id, worker_headers).status_code == 200

    response = review(client, milestone_id, owner_headers, "approve")

    assert response.status_code == 200
    milestone = response.json()
    assert milestone["status"] == "approved"
    assert milestone["reviewed_at"] is not None

    events = get_events(client, contract_id, owner_headers)
    assert events[-1]["event_type"] == "review_approved"

    # Approved is terminal: no more submit, review, edit, or delete.
    assert submit(client, milestone_id, worker_headers).status_code == 400
    assert review(client, milestone_id, owner_headers, "approve").status_code == 400
    assert client.patch(
        f"/milestones/{milestone_id}",
        headers=owner_headers,
        json={"title": "Nope"},
    ).status_code == 400
    assert client.delete(
        f"/milestones/{milestone_id}", headers=owner_headers
    ).status_code == 400


def test_changes_requested_lets_the_worker_resubmit_and_history_survives(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "changes"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]
    first_note = "First version of the deliverable."
    assert submit(client, milestone_id, worker_headers, note=first_note).status_code == 200

    response = review(
        client,
        milestone_id,
        owner_headers,
        "request_changes",
        note="Please fix the color contrast.",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "changes_requested"

    second_note = "Second version with the contrast fixed."
    resubmit = submit(client, milestone_id, worker_headers, note=second_note)
    assert resubmit.status_code == 200
    assert resubmit.json()["status"] == "submitted"
    # The milestone shows the latest submission...
    assert resubmit.json()["submission_note"] == second_note

    # ...but the event log preserves both deliverables.
    submissions = [
        e for e in get_events(client, contract_id, owner_headers)
        if e["event_type"] == "milestone_submitted"
    ]
    assert [e["note"] for e in submissions] == [first_note, second_note]


def test_requesting_changes_requires_a_note(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "changes-note"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]
    assert submit(client, milestone_id, worker_headers).status_code == 200

    response = review(client, milestone_id, owner_headers, "request_changes")
    assert response.status_code == 422


def test_cannot_review_a_milestone_that_is_not_submitted(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "review-early")
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]

    assert review(client, milestone_id, owner_headers, "approve").status_code == 400


# --- Complete and cancel -------------------------------------------------


def test_client_can_complete_a_contract_when_no_milestones_are_open(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "complete"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]
    assert submit(client, milestone_id, worker_headers).status_code == 200
    assert review(client, milestone_id, owner_headers, "approve").status_code == 200

    response = client.post(
        f"/contracts/{contract_id}/complete", headers=owner_headers
    )

    assert response.status_code == 200
    contract = response.json()
    assert contract["status"] == "completed"
    assert contract["completed_at"] is not None
    assert contract["milestones"][0]["status"] == "approved"

    events = get_events(client, contract_id, owner_headers)
    assert events[-1]["event_type"] == "contract_completed"


def test_client_can_complete_a_contract_with_no_milestones_at_all(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "complete-none")

    response = client.post(
        f"/contracts/{contract_id}/complete", headers=owner_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_cannot_complete_a_contract_with_open_milestones(client):
    _, owner_headers, _, _, contract_id = setup_contract(
        client, "complete-open"
    )
    add_milestone(client, contract_id, owner_headers)

    response = client.post(
        f"/contracts/{contract_id}/complete", headers=owner_headers
    )
    assert response.status_code == 400


def test_only_the_client_can_complete_or_cancel(client):
    _, _, _, worker_headers, contract_id = setup_contract(
        client, "complete-authz"
    )

    complete = client.post(
        f"/contracts/{contract_id}/complete", headers=worker_headers
    )
    assert complete.status_code == 403

    cancel = client.post(
        f"/contracts/{contract_id}/cancel", headers=worker_headers
    )
    assert cancel.status_code == 403


def test_cancelling_a_contract_cancels_its_open_milestones(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "cancel"
    )
    approved_id = add_milestone(client, contract_id, owner_headers, title="Milestone 1").json()["id"]
    pending_id = add_milestone(client, contract_id, owner_headers, title="Milestone 2").json()["id"]
    submitted_id = add_milestone(client, contract_id, owner_headers, title="Milestone 3").json()["id"]
    assert submit(client, approved_id, worker_headers).status_code == 200
    assert review(client, approved_id, owner_headers, "approve").status_code == 200
    assert submit(client, submitted_id, worker_headers).status_code == 200

    response = client.post(
        f"/contracts/{contract_id}/cancel", headers=owner_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    milestones = get_detail(client, contract_id, owner_headers)["milestones"]
    statuses = {m["id"]: m["status"] for m in milestones}
    assert statuses[approved_id] == "approved"  # approved work is untouched
    assert statuses[pending_id] == "cancelled"
    assert statuses[submitted_id] == "cancelled"

    events = get_events(client, contract_id, owner_headers)
    assert events[-1]["event_type"] == "contract_cancelled"

    # A cancelled contract rejects all further activity.
    assert add_milestone(client, contract_id, owner_headers).status_code == 400
    assert submit(client, pending_id, worker_headers).status_code == 400
    assert client.post(
        f"/contracts/{contract_id}/complete", headers=owner_headers
    ).status_code == 400


# --- Events, failures, and edge cases -------------------------------------


def test_contract_events_are_returned_in_chronological_order(client):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "chronology"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]
    assert submit(client, milestone_id, worker_headers, note="First attempt here.").status_code == 200
    assert review(
        client, milestone_id, owner_headers, "request_changes",
        note="Needs more detail.",
    ).status_code == 200
    assert submit(client, milestone_id, worker_headers, note="Second attempt here.").status_code == 200
    assert review(client, milestone_id, owner_headers, "approve").status_code == 200
    assert client.post(
        f"/contracts/{contract_id}/complete", headers=owner_headers
    ).status_code == 200

    events = get_events(client, contract_id, owner_headers)
    assert [e["event_type"] for e in events] == [
        "contract_created",
        "milestone_added",
        "milestone_submitted",
        "changes_requested",
        "milestone_submitted",
        "review_approved",
        "contract_completed",
    ]


def test_failed_submit_rolls_back_and_leaks_nothing(client, monkeypatch):
    _, owner_headers, _, worker_headers, contract_id = setup_contract(
        client, "rollback"
    )
    milestone_id = add_milestone(client, contract_id, owner_headers).json()["id"]

    def fail_commit(self):
        raise SQLAlchemyError("Sensitive database details")

    monkeypatch.setattr(Session, "commit", fail_commit)

    response = submit(client, milestone_id, worker_headers)

    assert response.status_code == 503
    assert "Sensitive database details" not in response.text

    monkeypatch.undo()

    milestones = get_detail(client, contract_id, owner_headers)["milestones"]
    assert milestones[0]["status"] == "pending"
    assert milestones[0]["submission_note"] is None


def test_milestone_endpoints_require_authentication(client):
    assert client.post("/contracts/1/milestones", json={"title": "x"}).status_code == 401
    assert client.patch("/milestones/1", json={"title": "x"}).status_code == 401
    assert client.delete("/milestones/1").status_code == 401
    assert client.post("/milestones/1/submit", json={"note": "x"}).status_code == 401
    assert client.post("/milestones/1/review", json={"decision": "approve"}).status_code == 401
    assert client.post("/contracts/1/complete").status_code == 401
    assert client.post("/contracts/1/cancel").status_code == 401


def test_missing_resources_return_404(client):
    _, owner_headers, _, worker_headers, _ = setup_contract(client, "missing")

    assert client.patch(
        "/milestones/9999", headers=owner_headers, json={"title": "Valid title"}
    ).status_code == 404
    assert client.delete("/milestones/9999", headers=owner_headers).status_code == 404
    assert submit(client, 9999, worker_headers).status_code == 404
    assert review(client, 9999, owner_headers, "approve").status_code == 404
    assert add_milestone(client, 9999, owner_headers).status_code == 404
    assert client.post("/contracts/9999/complete", headers=owner_headers).status_code == 404
    assert client.post("/contracts/9999/cancel", headers=owner_headers).status_code == 404


def test_milestone_input_validation(client):
    _, owner_headers, _, _, contract_id = setup_contract(client, "validation")

    # Whitespace-only or too-short titles are rejected before storage.
    assert add_milestone(client, contract_id, owner_headers, title="   ").status_code == 422
    assert add_milestone(client, contract_id, owner_headers, title="ab").status_code == 422
    # Zero and negative amounts are rejected.
    assert add_milestone(client, contract_id, owner_headers, amount="0").status_code == 422
    assert add_milestone(client, contract_id, owner_headers, amount="-50").status_code == 422
    # Whitespace-only descriptions become null rather than empty strings.
    response = add_milestone(client, contract_id, owner_headers, description="   ")
    assert response.status_code == 201
    assert response.json()["description"] is None
