"""add subscription fields to users

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, Sequence[str], None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "stripe_customer_id",
            sa.String(100),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_users_stripe_customer_id", "users", ["stripe_customer_id"]
    )
    op.create_index(
        "ix_users_stripe_customer_id", "users", ["stripe_customer_id"], unique=True
    )

    op.add_column(
        "users",
        sa.Column(
            "subscription_status",
            sa.String(30),
            nullable=False,
            server_default="trialing",
        ),
    )
    op.add_column(
        "users",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("subscription_ends_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Data migration: give existing confirmed users a 30-day grace trial period
    # so they are not immediately locked out after the upgrade.
    op.execute(
        """
        UPDATE users
        SET trial_ends_at = created_at + INTERVAL '30 days'
        WHERE email_confirmed = true
          AND subscription_status = 'trialing'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_constraint("uq_users_stripe_customer_id", "users", type_="unique")
    op.drop_column("users", "subscription_ends_at")
    op.drop_column("users", "trial_ends_at")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "stripe_customer_id")
