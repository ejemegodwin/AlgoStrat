"""add payouts table, provider reference, nullable txn contract

Payments (ADR-012): payouts record worker withdrawals of settled
earnings; ledger transactions gain the provider's reference for
reconciliation, and contract_id goes nullable because payout
settlements are user-level, not contract-level.

Downgrade fails if any payout settlement (contract_id NULL) exists —
delete those rows first (they have idempotency keys 'payout:%').

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = "a5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ledger_transactions",
        sa.Column("provider_reference", sa.String(100), nullable=True),
    )
    op.alter_column("ledger_transactions", "contract_id", nullable=True)

    op.create_table(
        "payouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "worker_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("destination", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider_reference", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payouts_amount_positive"),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name="ck_payouts_status"
        ),
    )
    op.create_index("ix_payouts_worker_id", "payouts", ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_payouts_worker_id", table_name="payouts")
    op.drop_table("payouts")
    op.alter_column("ledger_transactions", "contract_id", nullable=False)
    op.drop_column("ledger_transactions", "provider_reference")
