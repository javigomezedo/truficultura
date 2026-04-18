"""add water flow lps to plots

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plots", sa.Column("water_flow_lps", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("plots", "water_flow_lps")
