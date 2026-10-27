"""normalize user emails to lowercase

Lowercases all stored email addresses so that account uniqueness is
case-insensitive, matching the application-level normalization added to
registration and login.

If two existing accounts would collide after lowercasing (for example
"User@example.com" and "user@example.com"), the migration aborts and
lists the conflicting addresses instead of silently merging accounts.
Resolve those accounts manually, then rerun the migration.

This migration is not reversible: the original casing is lost.

Revision ID: 7a2b3c4d5e6f
Revises: 9c4f1a2b7d3e
Create Date: 2026-10-27 12:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "9c4f1a2b7d3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Lowercase stored emails, refusing to merge duplicate accounts."""
    connection = op.get_bind()

    duplicates = connection.execute(
        sa.text(
            "SELECT LOWER(email) AS normalized_email "
            "FROM users "
            "GROUP BY LOWER(email) "
            "HAVING COUNT(*) > 1"
        )
    ).fetchall()

    if duplicates:
        conflicting = sorted(row[0] for row in duplicates)
        raise RuntimeError(
            "Cannot normalize emails: these addresses are used by more "
            "than one account and must be resolved manually first: "
            + ", ".join(conflicting)
        )

    connection.execute(
        sa.text("UPDATE users SET email = LOWER(email)")
    )


def downgrade() -> None:
    """Irreversible: the original email casing cannot be restored."""
    pass
