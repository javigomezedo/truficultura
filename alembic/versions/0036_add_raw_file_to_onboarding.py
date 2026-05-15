"""Add raw_file column to onboarding_sessions.

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "onboarding_sessions",
        sa.Column("raw_file", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("onboarding_sessions", "raw_file")
