"""worker profile details + verified flag on profile tags

Worker profiles gain optional presentation fields (headline, bio,
country, timezone). Profile tags gain a verified flag that only
platform processes may set — workers declare skills, they can never
self-verify (§10: the self_reported vs verified split is structural).

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op


revision = "a1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_profiles",
        sa.Column("headline", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "worker_profiles", sa.Column("bio", sa.Text(), nullable=True)
    )
    op.add_column(
        "worker_profiles",
        sa.Column("country", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "worker_profiles",
        sa.Column("timezone", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "profile_tags",
        sa.Column(
            "verified",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("profile_tags", "verified")
    op.drop_column("worker_profiles", "timezone")
    op.drop_column("worker_profiles", "country")
    op.drop_column("worker_profiles", "bio")
    op.drop_column("worker_profiles", "headline")
