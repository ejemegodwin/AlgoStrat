from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db_session import get_db
from app.models import LedgerTransaction
from app.routers.contracts import load_contract, require_party
from app.schemas import LedgerAccountBalance, LedgerTransactionResponse
from app.services import ledger as ledger_service

router = APIRouter(tags=["ledger"])


@router.get("/ledger/balance", response_model=list[LedgerAccountBalance])
def get_my_balance(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # Users only ever see their own position; there is no endpoint that
    # exposes other users' or the platform's books.
    return ledger_service.user_balances(db, user_id)


@router.get(
    "/contracts/{contract_id}/ledger",
    response_model=list[LedgerTransactionResponse],
)
def get_contract_ledger(
    contract_id: int,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    contract = load_contract(contract_id, db)
    require_party(contract, user_id)

    return (
        db.query(LedgerTransaction)
        .filter(LedgerTransaction.contract_id == contract_id)
        .order_by(LedgerTransaction.created_at.asc(), LedgerTransaction.id.asc())
        .all()
    )
