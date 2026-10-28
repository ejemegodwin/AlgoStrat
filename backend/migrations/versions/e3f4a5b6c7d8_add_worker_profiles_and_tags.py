"""add worker profiles and profile tags

Introduces the data matching scores are computed from (ADR-010):
availability and minimum budget on worker_profiles, plus normalized
free-form skill/category tags. Purely additive.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-28 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the worker profile and profile tag tables."""
    op.create_table(
        "worker_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("availability", sa.String(length=20), nullable=False),
        sa.Column("min_budget", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_worker_profiles_user"),
        sa.CheckConstraint(
            "availability IN ('available', 'busy', 'unavailable')",
            name="ck_worker_profiles_availability",
        ),
    )

    op.create_table(
        "profile_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("value", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "value", name="uq_profile_tag"),
        sa.CheckConstraint(
            "kind IN ('skill', 'category')", name="ck_profile_tags_kind"
        ),
    )
    op.create_index("ix_profile_tags_user_id", "profile_tags", ["user_id"])


def downgrade() -> None:
    """Drop the profile tables."""
    op.drop_index("ix_profile_tags_user_id", table_name="profile_tags")
    op.drop_table("profile_tags")
    op.drop_table("worker_profiles")
