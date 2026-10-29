"""work receipts

Tamper-evident proof of verified completion: one row per completed
contract holding the canonical payload, its SHA-256 content hash, and
the server-side HMAC signature. Receipts are append-only — the API
never updates or deletes them, and corrections would be new superseding
records. contract_id is unique so a completion can never gain a second,
rewritten receipt.

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op


revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_uuid", sa.String(length=36), nullable=False),
        sa.Column(
            "worker_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "contract_id",
            sa.Integer(),
            sa.ForeignKey("contracts.id"),
            nullable=False,
        ),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("contract_id", name="uq_work_receipts_contract"),
        sa.UniqueConstraint("receipt_uuid", name="uq_work_receipts_uuid"),
    )
    op.create_index(
        "ix_work_receipts_receipt_uuid", "work_receipts", ["receipt_uuid"]
    )
    op.create_index("ix_work_receipts_worker_id", "work_receipts", ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_work_receipts_worker_id", table_name="work_receipts")
    op.drop_index("ix_work_receipts_receipt_uuid", table_name="work_receipts")
    op.drop_table("work_receipts")
