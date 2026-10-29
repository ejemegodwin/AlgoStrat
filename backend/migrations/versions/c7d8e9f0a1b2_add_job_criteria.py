"""job criteria — written acceptance criteria on jobs

The backbone of the verifiable-work thesis: reviews evaluate against
these criteria and completion receipts snapshot them. Editable while
the job is open and contract-free; locked thereafter by the API.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op


revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_criteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column(
            "required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_job_criteria_job_id", "job_criteria", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_criteria_job_id", table_name="job_criteria")
    op.drop_table("job_criteria")
