"""submissions history + contract criteria snapshot

Every work submission becomes its own record (note + evidence refs +
review outcome), giving reviews, disputes, and receipts a real evidence
trail. Contracts gain an immutable snapshot of the job's acceptance
criteria, written once at hire time.

Schema only: milestones submitted before this change keep their state
on the milestone row and simply have no submission records (the API
treats missing submissions as an empty history).

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op


revision = "e9f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "milestone_id",
            sa.Integer(),
            sa.ForeignKey("milestones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column(
            "evidence", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("review_decision", sa.String(length=20), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_submissions_milestone_id", "submissions", ["milestone_id"]
    )

    op.add_column(
        "contracts",
        sa.Column(
            "criteria_snapshot",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("contracts", "criteria_snapshot")
    op.drop_index("ix_submissions_milestone_id", table_name="submissions")
    op.drop_table("submissions")
