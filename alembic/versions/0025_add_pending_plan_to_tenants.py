"""add pending_plan to tenants

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("pending_plan", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "pending_plan")
