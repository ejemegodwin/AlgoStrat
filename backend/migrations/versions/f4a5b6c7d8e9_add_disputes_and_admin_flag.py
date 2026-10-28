"""add disputes table and users.is_admin, widen contract status check

Disputes (ADR-011): either contract party can raise one open dispute per
contract; while open, the contract sits in the new 'disputed' status,
which freezes all mutations via the existing require_active checks.
Resolution is admin-only; admins are ordinary users with is_admin set,
seeded manually via SQL.

Widening ck_contracts_status is safe on upgrade. Downgrade recreates
the constraint WITHOUT 'disputed', so it fails if any disputed or
dispute-resolved contracts exist — resolve/delete them first.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "disputes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "contract_id",
            sa.Integer(),
            sa.ForeignKey("contracts.id"),
            nullable=False,
        ),
        sa.Column(
            "milestone_id",
            sa.Integer(),
            sa.ForeignKey("milestones.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "raised_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'resolved')", name="ck_disputes_status"
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN "
            "('worker_favored', 'client_favored', 'dismissed')",
            name="ck_disputes_resolution",
        ),
    )
    op.create_index("ix_disputes_contract_id", "disputes", ["contract_id"])
    # One open dispute per contract (ADR-011), enforced by the database.
    op.create_index(
        "uq_disputes_one_open_per_contract",
        "disputes",
        ["contract_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        sqlite_where=sa.text("status = 'open'"),
    )

    # Widen the contract status CHECK to include 'disputed'.
    op.drop_constraint("ck_contracts_status", "contracts", type_="check")
    op.create_check_constraint(
        "ck_contracts_status",
        "contracts",
        "status IN ('active', 'completed', 'cancelled', 'disputed')",
    )


def downgrade() -> None:
    # Fails if any contract is currently 'disputed' — resolve disputes
    # before downgrading.
    op.drop_constraint("ck_contracts_status", "contracts", type_="check")
    op.create_check_constraint(
        "ck_contracts_status",
        "contracts",
        "status IN ('active', 'completed', 'cancelled')",
    )

    op.drop_index("uq_disputes_one_open_per_contract", table_name="disputes")
    op.drop_index("ix_disputes_contract_id", table_name="disputes")
    op.drop_table("disputes")

    op.drop_column("users", "is_admin")
