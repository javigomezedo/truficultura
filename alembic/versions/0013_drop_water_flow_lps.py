"""drop water_flow_lps from plots, backfill caudal_riego

Backfills caudal_riego (m³/h) from water_flow_lps (l/s) via * 3.6 for rows
that have water_flow_lps set but caudal_riego NULL, then drops water_flow_lps.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, Sequence[str], None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Backfill caudal_riego (m³/h) from water_flow_lps (l/s) where not yet set
    op.execute(
        "UPDATE plots SET caudal_riego = water_flow_lps * 3.6 "
        "WHERE water_flow_lps IS NOT NULL AND caudal_riego IS NULL"
    )
    op.drop_column("plots", "water_flow_lps")


def downgrade() -> None:
    op.add_column("plots", sa.Column("water_flow_lps", sa.Float(), nullable=True))
    # Restore approximate values (m³/h → l/s)
    op.execute(
        "UPDATE plots SET water_flow_lps = caudal_riego / 3.6 "
        "WHERE caudal_riego IS NOT NULL"
    )
