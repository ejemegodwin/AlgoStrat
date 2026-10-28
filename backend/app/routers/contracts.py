from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db_session import get_db
from app.models import Contract, ContractEvent, Milestone
from app.schemas import (
    ContractDetailResponse,
    ContractEventResponse,
    ContractResponse,
    MilestoneCreate,
    MilestoneResponse,
    MilestoneReview,
    MilestoneSubmit,
    MilestoneUpdate,
)

router = APIRouter(tags=["contracts"])

# Milestones in these statuses block contract completion and get
# cancelled if the contract is cancelled. "approved" is terminal.
OPEN_MILESTONE_STATUSES = ("pending", "submitted", "changes_requested")


def load_contract(contract_id: int, db: Session, for_update: bool = False) -> Contract:
    query = db.query(Contract).filter(Contract.id == contract_id)
    if for_update:
        # Mutations serialize on the contract row (ADR-008), the same
        # pattern the job row provides for hiring (ADR-001).
        query = query.with_for_update()
    contract = query.first()

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found.",
        )

    return contract


def load_milestone_with_locked_contract(
    milestone_id: int, db: Session
) -> tuple[Milestone, Contract]:
    milestone = db.query(Milestone).filter(Milestone.id == milestone_id).first()

    if milestone is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Milestone not found.",
        )

    contract = load_contract(milestone.contract_id, db, for_update=True)
    return milestone, contract


def require_party(contract: Contract, user_id: int) -> None:
    # Only the two parties may ever see a contract; the path id alone
    # must never grant access (no insecure direct object references).
    if user_id not in (contract.client_id, contract.worker_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a party to this contract.",
        )


def require_client(contract: Contract, user_id: int) -> None:
    if contract.client_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the client can perform this action.",
        )


def require_worker(contract: Contract, user_id: int) -> None:
    if contract.worker_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the worker can perform this action.",
        )


def require_active(contract: Contract) -> None:
    if contract.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This contract is no longer active.",
        )


def check_milestone_budget(
    contract: Contract,
    db: Session,
    new_amount: Decimal | None,
    exclude_milestone_id: int | None = None,
) -> None:
    """Money rule (ADR-008): when the contract has an agreed amount, the
    sum of non-cancelled milestone amounts may not exceed it."""
    if contract.agreed_amount is None or new_amount is None:
        return

    query = db.query(
        func.coalesce(func.sum(Milestone.amount), 0)
    ).filter(
        Milestone.contract_id == contract.id,
        Milestone.status != "cancelled",
        Milestone.amount.is_not(None),
    )
    if exclude_milestone_id is not None:
        query = query.filter(Milestone.id != exclude_milestone_id)

    allocated = query.scalar()

    if allocated + new_amount > contract.agreed_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Milestone amounts cannot exceed the contract's "
                "agreed amount."
            ),
        )


def record_event(
    db: Session,
    contract_id: int,
    actor_id: int,
    event_type: str,
    milestone_id: int | None = None,
    note: str | None = None,
) -> None:
    db.add(
        ContractEvent(
            contract_id=contract_id,
            milestone_id=milestone_id,
            actor_id=actor_id,
            event_type=event_type,
            note=note,
        )
    )


def commit_or_503(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to save changes right now. Please try again later.",
        ) from exc


@router.get("/contracts", response_model=list[ContractResponse])
def list_my_contracts(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(Contract)
        .filter(
            (Contract.client_id == user_id) | (Contract.worker_id == user_id)
        )
        .order_by(Contract.created_at.desc(), Contract.id.desc())
        .all()
    )


@router.get("/contracts/{contract_id}", response_model=ContractDetailResponse)
def get_contract(
    contract_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    contract = load_contract(contract_id, db)
    require_party(contract, user_id)
    return contract


@router.get(
    "/contracts/{contract_id}/events",
    response_model=list[ContractEventResponse],
)
def list_contract_events(
    contract_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    contract = load_contract(contract_id, db)
    require_party(contract, user_id)

    return (
        db.query(ContractEvent)
        .filter(ContractEvent.contract_id == contract_id)
        .order_by(ContractEvent.created_at.asc(), ContractEvent.id.asc())
        .all()
    )


@router.post(
    "/contracts/{contract_id}/milestones",
    response_model=MilestoneResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_milestone(
    contract_id: int,
    milestone_data: MilestoneCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    contract = load_contract(contract_id, db, for_update=True)
    require_client(contract, user_id)
    require_active(contract)
    check_milestone_budget(contract, db, milestone_data.amount)

    position = milestone_data.position
    if position is None:
        position = db.query(
            func.coalesce(func.max(Milestone.position), 0)
        ).filter(Milestone.contract_id == contract.id).scalar() + 1

    milestone = Milestone(
        contract_id=contract.id,
        title=milestone_data.title,
        description=milestone_data.description,
        amount=milestone_data.amount,
        due_date=milestone_data.due_date,
        position=position,
    )
    db.add(milestone)
    db.flush()  # assign milestone.id before writing its first event
    record_event(
        db, contract.id, user_id, "milestone_added", milestone_id=milestone.id
    )

    commit_or_503(db)
    db.refresh(milestone)
    return milestone


@router.patch("/milestones/{milestone_id}", response_model=MilestoneResponse)
def update_milestone(
    milestone_id: int,
    milestone_data: MilestoneUpdate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    milestone, contract = load_milestone_with_locked_contract(milestone_id, db)
    require_client(contract, user_id)
    require_active(contract)

    if milestone.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending milestones can be edited.",
        )

    updates = milestone_data.model_dump(exclude_unset=True)
    if not updates:
        return milestone

    if "amount" in updates:
        check_milestone_budget(
            contract,
            db,
            updates["amount"],
            exclude_milestone_id=milestone.id,
        )

    for field, value in updates.items():
        setattr(milestone, field, value)

    record_event(
        db, contract.id, user_id, "milestone_updated", milestone_id=milestone.id
    )

    commit_or_503(db)
    db.refresh(milestone)
    return milestone


@router.delete(
    "/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_milestone(
    milestone_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    milestone, contract = load_milestone_with_locked_contract(milestone_id, db)
    require_client(contract, user_id)
    require_active(contract)

    if milestone.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending milestones can be deleted.",
        )

    # Keep the audit trail consistent on every database: unlink this
    # milestone's events before deleting it (ON DELETE SET NULL is the
    # database-level backstop, but SQLite only enforces it with foreign
    # keys enabled).
    db.query(ContractEvent).filter(
        ContractEvent.milestone_id == milestone.id
    ).update({"milestone_id": None}, synchronize_session=False)

    title = milestone.title
    db.delete(milestone)
    record_event(db, contract.id, user_id, "milestone_removed", note=title)

    commit_or_503(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/milestones/{milestone_id}/submit", response_model=MilestoneResponse)
def submit_milestone(
    milestone_id: int,
    submit_data: MilestoneSubmit,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    milestone, contract = load_milestone_with_locked_contract(milestone_id, db)
    require_worker(contract, user_id)
    require_active(contract)

    if milestone.status not in ("pending", "changes_requested"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending or changes-requested milestones can be submitted.",
        )

    milestone.status = "submitted"
    milestone.submission_note = submit_data.note
    milestone.submitted_at = datetime.now(timezone.utc)
    record_event(
        db,
        contract.id,
        user_id,
        "milestone_submitted",
        milestone_id=milestone.id,
        note=submit_data.note,
    )

    commit_or_503(db)
    db.refresh(milestone)
    return milestone


@router.post("/milestones/{milestone_id}/review", response_model=MilestoneResponse)
def review_milestone(
    milestone_id: int,
    review_data: MilestoneReview,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    milestone, contract = load_milestone_with_locked_contract(milestone_id, db)
    require_client(contract, user_id)
    require_active(contract)

    if milestone.status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only submitted milestones can be reviewed.",
        )

    milestone.reviewed_at = datetime.now(timezone.utc)

    if review_data.decision == "approve":
        milestone.status = "approved"
        event_type = "review_approved"
    else:
        milestone.status = "changes_requested"
        event_type = "changes_requested"

    record_event(
        db,
        contract.id,
        user_id,
        event_type,
        milestone_id=milestone.id,
        note=review_data.note,
    )

    commit_or_503(db)
    db.refresh(milestone)
    return milestone


@router.post(
    "/contracts/{contract_id}/complete",
    response_model=ContractDetailResponse,
)
def complete_contract(
    contract_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    contract = load_contract(contract_id, db, for_update=True)
    require_client(contract, user_id)
    require_active(contract)

    open_milestones = db.query(func.count(Milestone.id)).filter(
        Milestone.contract_id == contract.id,
        Milestone.status.in_(OPEN_MILESTONE_STATUSES),
    ).scalar()

    if open_milestones:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "All milestones must be approved or cancelled before "
                "the contract can be completed."
            ),
        )

    contract.status = "completed"
    contract.completed_at = datetime.now(timezone.utc)
    record_event(db, contract.id, user_id, "contract_completed")

    commit_or_503(db)
    db.refresh(contract)
    return contract


@router.post(
    "/contracts/{contract_id}/cancel",
    response_model=ContractDetailResponse,
)
def cancel_contract(
    contract_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    contract = load_contract(contract_id, db, for_update=True)
    require_client(contract, user_id)
    require_active(contract)

    contract.status = "cancelled"
    db.query(Milestone).filter(
        Milestone.contract_id == contract.id,
        Milestone.status.in_(OPEN_MILESTONE_STATUSES),
    ).update({"status": "cancelled"}, synchronize_session=False)
    record_event(db, contract.id, user_id, "contract_cancelled")

    commit_or_503(db)
    db.refresh(contract)
    return contract
