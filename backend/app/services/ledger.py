"""Internal payment ledger (ADR-009).

Records who owes what to whom using double-entry bookkeeping: every
transaction's entries sum to zero, balances are derived (never stored),
and corrections are reversal transactions, never edits.

No real money moves here. Settlement arrives with a payment-provider
integration; refunds and reversals arrive with the disputes increment.
"""

import os
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Contract, LedgerAccount, LedgerEntry, LedgerTransaction, Milestone

# Platform fee, configurable per environment (ADR-009). Read once at
# import; tests monkeypatch this module attribute to vary it.
PLATFORM_FEE_PERCENT = Decimal(os.getenv("PLATFORM_FEE_PERCENT", "0"))

# Sign conventions: a debit-normal account's natural balance is
# SUM(entries); a credit-normal account's natural balance is -SUM.
# Under normal operation every natural balance is non-negative.
DEBIT_NORMAL_ACCOUNT_TYPES = frozenset({"client_payable", "platform_cash"})
CREDIT_NORMAL_ACCOUNT_TYPES = frozenset({"worker_receivable", "platform_revenue"})

ZERO_CENTS = Decimal("0.01")


def get_platform_fee_percent() -> Decimal:
    return PLATFORM_FEE_PERCENT


def get_or_create_account(
    db: Session,
    owner_type: str,
    owner_id: int | None,
    account_type: str,
    currency: str,
) -> LedgerAccount:
    account = (
        db.query(LedgerAccount)
        .filter(
            LedgerAccount.owner_type == owner_type,
            LedgerAccount.owner_id == owner_id,
            LedgerAccount.account_type == account_type,
            LedgerAccount.currency == currency,
        )
        .first()
    )

    if account is None:
        account = LedgerAccount(
            owner_type=owner_type,
            owner_id=owner_id,
            account_type=account_type,
            currency=currency,
        )
        db.add(account)
        db.flush()

    return account


def post_accrual(
    db: Session,
    *,
    milestone: Milestone,
    contract: Contract,
    actor_id: int,
) -> LedgerTransaction | None:
    """Record the obligation created by approving a priced milestone.

    Runs inside the caller's transaction (the review endpoint holds the
    contract row lock), so approval and accrual commit or roll back
    together. Idempotent via the milestone-scoped key: a retried call
    returns the original transaction instead of double-posting.
    """
    if milestone.amount is None:
        return None

    idempotency_key = f"accrual:milestone:{milestone.id}"
    existing = (
        db.query(LedgerTransaction)
        .filter(LedgerTransaction.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        return existing

    amount = milestone.amount
    fee = (amount * get_platform_fee_percent() / Decimal(100)).quantize(
        ZERO_CENTS, rounding=ROUND_HALF_UP
    )
    # The worker receives the remainder, so the entries balance exactly.
    net = amount - fee

    transaction = LedgerTransaction(
        contract_id=contract.id,
        milestone_id=milestone.id,
        type="accrual",
        idempotency_key=idempotency_key,
        created_by=actor_id,
        note=f"Accrual for milestone '{milestone.title}'.",
    )
    db.add(transaction)
    db.flush()

    client_account = get_or_create_account(
        db, "user", contract.client_id, "client_payable", contract.currency
    )
    worker_account = get_or_create_account(
        db, "user", contract.worker_id, "worker_receivable", contract.currency
    )

    db.add(
        LedgerEntry(
            transaction_id=transaction.id,
            account_id=client_account.id,
            amount=amount,
        )
    )
    db.add(
        LedgerEntry(
            transaction_id=transaction.id,
            account_id=worker_account.id,
            amount=-net,
        )
    )

    if fee > 0:
        platform_account = get_or_create_account(
            db, "platform", None, "platform_revenue", contract.currency
        )
        db.add(
            LedgerEntry(
                transaction_id=transaction.id,
                account_id=platform_account.id,
                amount=-fee,
            )
        )

    return transaction


def natural_balance(account_type: str, entries_total: Decimal) -> Decimal:
    """Report an account's position as a non-negative figure under
    normal operation: SUM for debit-normal accounts, -SUM for
    credit-normal ones."""
    if account_type in DEBIT_NORMAL_ACCOUNT_TYPES:
        return entries_total
    return -entries_total


def user_balances(db: Session, user_id: int) -> list[dict]:
    """The caller's derived balances, one row per account."""
    accounts = (
        db.query(LedgerAccount)
        .filter(LedgerAccount.owner_type == "user", LedgerAccount.owner_id == user_id)
        .order_by(LedgerAccount.account_type, LedgerAccount.currency)
        .all()
    )

    balances = []
    for account in accounts:
        total = db.query(
            func.coalesce(func.sum(LedgerEntry.amount), 0)
        ).filter(LedgerEntry.account_id == account.id).scalar()
        balances.append(
            {
                "account_type": account.account_type,
                "currency": account.currency,
                "balance": natural_balance(account.account_type, total),
            }
        )

    return balances
