"""add user profile fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add first_name column
    op.add_column(
        "users",
        sa.Column(
            "first_name",
            sa.String(100),
            nullable=False,
            server_default="User",
        ),
    )

    # Add last_name column
    op.add_column(
        "users",
        sa.Column(
            "last_name",
            sa.String(100),
            nullable=False,
            server_default="",
        ),
    )

    # Add email column with unique constraint
    op.add_column(
        "users",
        sa.Column(
            "email",
            sa.String(255),
            nullable=False,
            server_default="user@example.com",
            unique=True,
        ),
    )

    # Create index on email for performance
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_column("users", "email")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
