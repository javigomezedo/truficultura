"""add users table and user_id to plots, expenses, incomes

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Add user_id to plots (nullable — existing rows get NULL, assigned on first login)
    op.add_column(
        "plots",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )

    # Add user_id to expenses
    op.add_column(
        "expenses",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )

    # Add user_id to incomes
    op.add_column(
        "incomes",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("incomes", "user_id")
    op.drop_column("expenses", "user_id")
    op.drop_column("plots", "user_id")
    op.drop_table("users")
