"""Add stripe_subscription_id column to tenants table

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, Sequence[str], None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_tenants_stripe_subscription_id",
        "tenants",
        ["stripe_subscription_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_stripe_subscription_id", table_name="tenants")
    op.drop_column("tenants", "stripe_subscription_id")
