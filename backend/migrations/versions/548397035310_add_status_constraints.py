
"""add status constraints

Revision ID: 548397035310
Revises: aa54ab4261d0
Create Date: 2026-10-23 16:03:42.265999
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "548397035310"
down_revision: Union[str, Sequence[str], None] = "aa54ab4261d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Restrict status values at the database level."""
    op.create_check_constraint(
        "ck_jobs_status",
        "jobs",
        "status IN ('open', 'closed')",
    )

    op.create_check_constraint(
        "ck_job_applications_status",
        "job_applications",
        "status IN ('pending', 'accepted', 'rejected', 'withdrawn')",
    )


def downgrade() -> None:
    """Remove status constraints."""
    op.drop_constraint(
        "ck_job_applications_status",
        "job_applications",
        type_="check",
    )

    op.drop_constraint(
        "ck_jobs_status",
        "jobs",
        type_="check",
    )
