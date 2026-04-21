"""add water_flow_lps to plots and municipio_name to rainfall_records

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, Sequence[str], None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plots", sa.Column("water_flow_lps", sa.Float(), nullable=True))
    op.add_column(
        "rainfall_records",
        sa.Column("municipio_name", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rainfall_records", "municipio_name")
    op.drop_column("plots", "water_flow_lps")
