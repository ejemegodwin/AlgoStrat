"""add contracts, milestones, and contract events

Introduces the contract layer (ADR-008): a Contract is the receipt of a
hire, milestones are the client-defined agreement, and contract_events
is the append-only audit log that verifiable work history builds on.

Purely additive: creates three tables with constraints and indexes.
Existing rows are unaffected.

Revision ID: c1d2e3f4a5b6
Revises: 7a2b3c4d5e6f
Create Date: 2026-10-28 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "7a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the contract, milestone, and contract event tables."""
    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("agreed_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["job_applications.id"]),
        sa.ForeignKeyConstraint(["client_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="uq_contracts_application"),
        sa.UniqueConstraint("job_id", name="uq_contracts_job"),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_contracts_status",
        ),
    )
    op.create_index("ix_contracts_client_id", "contracts", ["client_id"])
    op.create_index("ix_contracts_worker_id", "contracts", ["worker_id"])

    op.create_table(
        "milestones",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("submission_note", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'submitted', 'changes_requested', "
            "'approved', 'cancelled')",
            name="ck_milestones_status",
        ),
    )
    op.create_index("ix_milestones_contract_id", "milestones", ["contract_id"])

    op.create_table(
        "contract_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contract_id", sa.Integer(), nullable=False),
        sa.Column("milestone_id", sa.Integer(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestones.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contract_events_contract_id", "contract_events", ["contract_id"]
    )


def downgrade() -> None:
    """Drop the contract layer tables."""
    op.drop_index("ix_contract_events_contract_id", table_name="contract_events")
    op.drop_table("contract_events")
    op.drop_index("ix_milestones_contract_id", table_name="milestones")
    op.drop_table("milestones")
    op.drop_index("ix_contracts_worker_id", table_name="contracts")
    op.drop_index("ix_contracts_client_id", table_name="contracts")
    op.drop_table("contracts")
