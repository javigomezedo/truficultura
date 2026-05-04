"""Add plan column to tenants table

Revision ID: 0023
Revises: 0022
Create Date: 2025-01-01

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: Union[str, Sequence[str], None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("plan", sa.String(20), nullable=True),
    )
    # Migrate existing active tenants to 'premium' so they don't lose access
    op.execute(
        "UPDATE tenants SET plan = 'premium' WHERE subscription_status = 'active'"
    )


def downgrade() -> None:
    op.drop_column("tenants", "plan")
