"""enforce single accepted application per job

Adds a partial unique index so that each job can have at most one
application with status 'accepted'. The index only covers accepted
rows, so any number of pending, rejected, or withdrawn applications
remain allowed.

Revision ID: 9c4f1a2b7d3e
Revises: 548397035310
Create Date: 2026-10-27 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9c4f1a2b7d3e"
down_revision: Union[str, Sequence[str], None] = "548397035310"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the single-hire partial unique index."""
    op.create_index(
        "uq_job_applications_one_accepted_per_job",
        "job_applications",
        ["job_id"],
        unique=True,
        sqlite_where=sa.text("status = 'accepted'"),
        postgresql_where=sa.text("status = 'accepted'"),
    )


def downgrade() -> None:
    """Remove the single-hire partial unique index."""
    op.drop_index(
        "uq_job_applications_one_accepted_per_job",
        table_name="job_applications",
    )
