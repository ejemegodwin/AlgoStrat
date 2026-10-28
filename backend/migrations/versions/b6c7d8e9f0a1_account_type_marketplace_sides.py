"""account_type becomes the marketplace side (ADR-018)

The column used to be a free string defaulting to 'individual' that
gated nothing. It now means the marketplace side — client, worker, or
both — enforced by a CHECK constraint and required at registration.

Existing accounts are grandfathered to 'both': they already could do
everything, so the backfill keeps their capabilities rather than
silently taking one side away.

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-10-28
"""

from alembic import op


revision = "b6c7d8e9f0a1"
down_revision = "a5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Backfill BEFORE the constraint: any legacy value (everyone was
    # 'individual') becomes 'both' — the capability-preserving choice.
    op.execute(
        "UPDATE users SET account_type = 'both' "
        "WHERE account_type NOT IN ('client', 'worker', 'both')"
    )
    op.create_check_constraint(
        "ck_users_account_type",
        "users",
        "account_type IN ('client', 'worker', 'both')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_account_type", "users", type_="check")
    op.execute("UPDATE users SET account_type = 'individual'")
