"""add visual_col to plants

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plants",
        sa.Column("visual_col", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute("UPDATE plants SET visual_col = col_order + 1")
    op.alter_column("plants", "visual_col", server_default=None)

    op.create_index(
        "ix_plant_user_plot_visual",
        "plants",
        ["user_id", "plot_id", "visual_col"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_plant_user_plot_visual", table_name="plants")
    op.drop_column("plants", "visual_col")
