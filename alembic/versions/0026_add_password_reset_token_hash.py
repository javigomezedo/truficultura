"""add password_reset_token_hash to users

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0026"
down_revision: str = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_reset_token_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_reset_token_hash")
