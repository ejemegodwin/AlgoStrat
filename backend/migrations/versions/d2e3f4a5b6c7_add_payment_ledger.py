"""add payment ledger tables

Introduces the internal double-entry ledger (ADR-009): accounts,
balanced transactions, and signed entries. Append-only; records
obligations only — no real money moves until a provider integration.

Purely additive: creates three tables with constraints and indexes.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-28 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ledger account, transaction, and entry tables."""
    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("account_type", sa.String(length=30), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_type",
            "owner_id",
            "account_type",
            "currency",
            name="uq_ledger_account",
        ),
        sa.CheckConstraint(
            "owner_type IN ('user', 'platform')",
            name="ck_ledger_accounts_owner_type",
        ),
        sa.CheckConstraint(
            "account_type IN ('client_payable', 'worker_receivable', "
            "'platform_revenue', 'platform_cash')",
            name="ck_ledger_accounts_type",
        ),
    )

    op.create_table(
        "ledger_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("milestone_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["milestone_id"], ["milestones.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_ledger_transactions_idempotency_key"
        ),
        sa.CheckConstraint(
            "type IN ('accrual', 'settlement', 'reversal', 'adjustment')",
            name="ck_ledger_transactions_type",
        ),
    )
    op.create_index(
        "ix_ledger_transactions_contract_id",
        "ledger_transactions",
        ["contract_id"],
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["ledger_accounts.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["ledger_transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "amount <> 0", name="ck_ledger_entries_amount_nonzero"
        ),
    )
    op.create_index(
        "ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"]
    )
    op.create_index(
        "ix_ledger_entries_account_id", "ledger_entries", ["account_id"]
    )


def downgrade() -> None:
    """Drop the ledger tables."""
    op.drop_index("ix_ledger_entries_account_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_transaction_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index(
        "ix_ledger_transactions_contract_id", table_name="ledger_transactions"
    )
    op.drop_table("ledger_transactions")
    op.drop_table("ledger_accounts")
