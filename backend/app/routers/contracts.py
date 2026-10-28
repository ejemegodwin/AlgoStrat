from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db_session import get_db
from app.models import Contract, ContractEvent
from app.schemas import (
    ContractDetailResponse,
    ContractEventResponse,
    ContractResponse,
)

router = APIRouter(tags=["contracts"])


def load_contract(contract_id: int, db: Session) -> Contract:
    contract = db.query(Contract).filter(Contract.id == contract_id).first()

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found.",
        )

    return contract


def require_party(contract: Contract, user_id: int) -> None:
    # Only the two parties may ever see a contract; the path id alone
    # must never grant access (no insecure direct object references).
    if user_id not in (contract.client_id, contract.worker_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a party to this contract.",
        )


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
