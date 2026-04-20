"""add_comunidad_regantes_recinto_caudal

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "comunidad_regantes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "plots",
        sa.Column(
            "recinto",
            sa.String(length=10),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "plots",
        sa.Column("caudal_riego", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plots", "caudal_riego")
    op.drop_column("plots", "recinto")
    op.drop_column("users", "comunidad_regantes")
