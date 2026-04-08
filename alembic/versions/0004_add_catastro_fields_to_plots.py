"""add provincia_cod and municipio_cod to plots

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("plots", sa.Column("provincia_cod", sa.String(10), nullable=True))
    op.add_column("plots", sa.Column("municipio_cod", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("plots", "municipio_cod")
    op.drop_column("plots", "provincia_cod")
