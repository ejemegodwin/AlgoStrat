"""structured jobs and application proposals

Jobs gain job_type / work_mode / deadline / min_worker_level with CHECK
constraints (starter tasks and placement checks require criteria — that
rule lives in the API, which knows the final state of an edit).
Applications gain proposed_price / proposed_currency / estimated_days.

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op


revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Server defaults backfill existing rows, then stay as safety nets.
    op.add_column(
        "jobs",
        sa.Column(
            "job_type",
            sa.String(length=20),
            nullable=False,
            server_default="standard",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "work_mode",
            sa.String(length=20),
            nullable=False,
            server_default="remote",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "min_worker_level",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_jobs_job_type",
        "jobs",
        "job_type IN ('standard', 'starter_task', 'placement_check')",
    )
    op.create_check_constraint(
        "ck_jobs_work_mode",
        "jobs",
        "work_mode IN ('remote', 'in_person')",
    )
    op.create_check_constraint(
        "ck_jobs_min_worker_level",
        "jobs",
        "min_worker_level BETWEEN 0 AND 3",
    )

    op.add_column(
        "job_applications",
        sa.Column("proposed_price", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column("proposed_currency", sa.String(length=3), nullable=True),
    )
    op.add_column(
        "job_applications",
        sa.Column("estimated_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_applications", "estimated_days")
    op.drop_column("job_applications", "proposed_currency")
    op.drop_column("job_applications", "proposed_price")

    op.drop_constraint("ck_jobs_min_worker_level", "jobs", type_="check")
    op.drop_constraint("ck_jobs_work_mode", "jobs", type_="check")
    op.drop_constraint("ck_jobs_job_type", "jobs", type_="check")
    op.drop_column("jobs", "min_worker_level")
    op.drop_column("jobs", "deadline")
    op.drop_column("jobs", "work_mode")
    op.drop_column("jobs", "job_type")
