"""public market-test waitlist leads

Revision ID: 1a2b3c4d5e6f
Revises: f0a1b2c3d4e5, b7c8d9e0f1a2
"""

import sqlalchemy as sa
from alembic import op


revision = "1a2b3c4d5e6f"
down_revision = ("f0a1b2c3d4e5", "b7c8d9e0f1a2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waitlist_leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("audience", sa.String(length=20), nullable=False),
        sa.Column("region", sa.String(length=30), nullable=True),
        sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "audience IN ('worker', 'business')",
            name="ck_waitlist_leads_audience",
        ),
        sa.CheckConstraint(
            "region IS NULL OR region IN ('africa', 'europe', 'middle-east', 'north-america', 'latin-america', 'asia-pacific')",
            name="ck_waitlist_leads_region",
        ),
        sa.UniqueConstraint("email", name="uq_waitlist_leads_email"),
    )
    op.create_index("ix_waitlist_leads_email", "waitlist_leads", ["email"])


def downgrade() -> None:
    op.drop_index("ix_waitlist_leads_email", table_name="waitlist_leads")
    op.drop_table("waitlist_leads")
