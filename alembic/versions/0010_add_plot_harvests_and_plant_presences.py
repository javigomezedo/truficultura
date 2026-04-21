"""add_plot_harvests_and_plant_presences

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plot_harvests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plot_id", sa.Integer(), nullable=False),
        sa.Column("harvest_date", sa.Date(), nullable=False),
        sa.Column("weight_grams", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plot_harvests_id"), "plot_harvests", ["id"], unique=False)
    op.create_index(
        op.f("ix_plot_harvests_user_id"), "plot_harvests", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_plot_harvests_plot_id"), "plot_harvests", ["plot_id"], unique=False
    )
    op.create_index(
        op.f("ix_plot_harvests_harvest_date"),
        "plot_harvests",
        ["harvest_date"],
        unique=False,
    )
    op.create_index(
        "ix_plot_harvest_user_plot",
        "plot_harvests",
        ["user_id", "plot_id"],
        unique=False,
    )
    op.create_index(
        "ix_plot_harvest_user_date",
        "plot_harvests",
        ["user_id", "harvest_date"],
        unique=False,
    )

    op.create_table(
        "plant_presences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plot_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("presence_date", sa.Date(), nullable=False),
        sa.Column("has_truffle", sa.Boolean(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plant_id", "presence_date", name="uq_plant_presence_per_day"
        ),
    )
    op.create_index(
        op.f("ix_plant_presences_id"), "plant_presences", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_plant_presences_user_id"), "plant_presences", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_plant_presences_plot_id"), "plant_presences", ["plot_id"], unique=False
    )
    op.create_index(
        op.f("ix_plant_presences_plant_id"),
        "plant_presences",
        ["plant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plant_presences_presence_date"),
        "plant_presences",
        ["presence_date"],
        unique=False,
    )
    op.create_index(
        "ix_plant_presence_user_plot",
        "plant_presences",
        ["user_id", "plot_id"],
        unique=False,
    )
    op.create_index(
        "ix_plant_presence_user_plot_date",
        "plant_presences",
        ["user_id", "plot_id", "presence_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_plant_presence_user_plot_date", table_name="plant_presences")
    op.drop_index("ix_plant_presence_user_plot", table_name="plant_presences")
    op.drop_index(
        op.f("ix_plant_presences_presence_date"), table_name="plant_presences"
    )
    op.drop_index(op.f("ix_plant_presences_plant_id"), table_name="plant_presences")
    op.drop_index(op.f("ix_plant_presences_plot_id"), table_name="plant_presences")
    op.drop_index(op.f("ix_plant_presences_user_id"), table_name="plant_presences")
    op.drop_index(op.f("ix_plant_presences_id"), table_name="plant_presences")
    op.drop_table("plant_presences")

    op.drop_index("ix_plot_harvest_user_date", table_name="plot_harvests")
    op.drop_index("ix_plot_harvest_user_plot", table_name="plot_harvests")
    op.drop_index(op.f("ix_plot_harvests_harvest_date"), table_name="plot_harvests")
    op.drop_index(op.f("ix_plot_harvests_plot_id"), table_name="plot_harvests")
    op.drop_index(op.f("ix_plot_harvests_user_id"), table_name="plot_harvests")
    op.drop_index(op.f("ix_plot_harvests_id"), table_name="plot_harvests")
    op.drop_table("plot_harvests")
