"""make rainfall_records.user_id nullable for shared AEMET/Ibericam records

Records with source='aemet' or source='ibericam' are now global (user_id=NULL).
Records with source='manual' keep their user_id (user-owned).

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, Sequence[str], None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "rainfall_records",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Before reverting, NULL values must be handled; delete shared records.
    op.execute(
        "DELETE FROM rainfall_records WHERE user_id IS NULL"
    )
    op.alter_column(
        "rainfall_records",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
