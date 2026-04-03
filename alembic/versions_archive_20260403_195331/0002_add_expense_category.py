"""add category column to expenses

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-22
"""

import sqlalchemy as sa
from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expenses", sa.Column("category", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("expenses", "category")
