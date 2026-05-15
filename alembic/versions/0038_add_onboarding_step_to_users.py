"""0038 – Add onboarding_step and onboarding_completed_at to users

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_step", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "onboarding_completed_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "onboarding_step")
