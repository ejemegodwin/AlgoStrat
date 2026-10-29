"""placement checks, variants and attempts (Phase 5)

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op


revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "placement_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("skill", sa.String(50), nullable=False, unique=True),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("learning_resources", sa.Text(), nullable=True),
        sa.Column("reviewer_guidance", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "placement_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "check_id",
            sa.Integer(),
            sa.ForeignKey("placement_checks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "criteria", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_placement_variants_check_id", "placement_variants", ["check_id"]
    )
    op.create_table(
        "placement_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "check_id",
            sa.Integer(),
            sa.ForeignKey("placement_checks.id"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            sa.Integer(),
            sa.ForeignKey("placement_variants.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("submission", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "reviewed_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('started', 'submitted', 'passed', 'not_yet')",
            name="ck_placement_attempts_status",
        ),
    )
    op.create_index(
        "ix_placement_attempts_user_id", "placement_attempts", ["user_id"]
    )
    op.create_index(
        "ix_placement_attempts_check_id", "placement_attempts", ["check_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_placement_attempts_check_id", "placement_attempts")
    op.drop_index("ix_placement_attempts_user_id", "placement_attempts")
    op.drop_table("placement_attempts")
    op.drop_index("ix_placement_variants_check_id", "placement_variants")
    op.drop_table("placement_variants")
    op.drop_table("placement_checks")
