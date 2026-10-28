from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db_session import get_db
from app.models import LedgerAccount, Payout
from app.routers.contracts import commit_or_503
from app.schemas import PayoutCreate, PayoutResponse
from app.services import ledger as ledger_service
from app.services import payments as payments_service

router = APIRouter(tags=["payouts"])


@router.post(
    "/payouts",
    response_model=PayoutResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_payout(
    payout_data: PayoutCreate,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    # Serialize on the worker's receivable account row (ADR-012) so
    # concurrent payout requests cannot double-spend the balance.
    account = (
        db.query(LedgerAccount)
        .filter(
            LedgerAccount.owner_type == "user",
            LedgerAccount.owner_id == user_id,
            LedgerAccount.account_type == "worker_receivable",
            LedgerAccount.currency == payout_data.currency,
        )
        .with_for_update()
        .first()
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have no earnings in this currency.",
        )

    available = ledger_service.account_natural_balance(db, account)
    amount = payout_data.amount if payout_data.amount is not None else available

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing available to pay out.",
        )
    if amount > available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payout amount exceeds your settled balance.",
        )

    # Receivables are cash-backed by definition; refuse rather than
    # overdraw if that invariant is ever broken.
    cash_account = ledger_service.get_or_create_account(
        db, "platform", None, "platform_cash", payout_data.currency
    )
    cash_available = ledger_service.account_natural_balance(db, cash_account)
    if amount > cash_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payouts are temporarily unavailable.",
        )

    payout = Payout(
        worker_id=user_id,
        amount=amount,
        currency=payout_data.currency,
        destination=payout_data.destination,
    )
    db.add(payout)
    db.flush()  # assign payout.id before keying the settlement on it

    transfer_reference = payments_service.get_provider().transfer(
        amount=amount,
        currency=payout_data.currency,
        reference=f"payout:{payout.id}",
        destination=payout_data.destination,
    )
    payout.provider_reference = transfer_reference

    ledger_service.post_payout_settlement(
        db, payout=payout, worker_account=account, actor_id=user_id
    )

    commit_or_503(db)
    db.refresh(payout)
    return payout


@router.get("/payouts", response_model=list[PayoutResponse])
def list_my_payouts(
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(Payout)
        .filter(Payout.worker_id == user_id)
        .order_by(Payout.created_at.desc(), Payout.id.desc())
        .all()
    )
