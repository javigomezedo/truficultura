"""add_plants_and_truffle_events

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plot_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("row_label", sa.String(length=10), nullable=False),
        sa.Column("row_order", sa.Integer(), nullable=False),
        sa.Column("col_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plot_id", "label", name="uq_plant_label_per_plot"),
        sa.UniqueConstraint(
            "plot_id", "row_order", "col_order", name="uq_plant_position_per_plot"
        ),
    )
    op.create_index(op.f("ix_plants_id"), "plants", ["id"], unique=False)
    op.create_index(op.f("ix_plants_plot_id"), "plants", ["plot_id"], unique=False)
    op.create_index(op.f("ix_plants_user_id"), "plants", ["user_id"], unique=False)
    op.create_index("ix_plant_user_plot", "plants", ["user_id", "plot_id"], unique=False)

    op.create_table(
        "truffle_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("plot_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undo_window_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_truffle_events_id"), "truffle_events", ["id"], unique=False)
    op.create_index(op.f("ix_truffle_events_plant_id"), "truffle_events", ["plant_id"], unique=False)
    op.create_index(op.f("ix_truffle_events_plot_id"), "truffle_events", ["plot_id"], unique=False)
    op.create_index(op.f("ix_truffle_events_user_id"), "truffle_events", ["user_id"], unique=False)
    op.create_index(
        "ix_truffle_event_user_plot_plant",
        "truffle_events",
        ["user_id", "plot_id", "plant_id"],
        unique=False,
    )
    op.create_index(
        "ix_truffle_event_plant_created",
        "truffle_events",
        ["plant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_truffle_event_plant_created", table_name="truffle_events")
    op.drop_index("ix_truffle_event_user_plot_plant", table_name="truffle_events")
    op.drop_index(op.f("ix_truffle_events_user_id"), table_name="truffle_events")
    op.drop_index(op.f("ix_truffle_events_plot_id"), table_name="truffle_events")
    op.drop_index(op.f("ix_truffle_events_plant_id"), table_name="truffle_events")
    op.drop_index(op.f("ix_truffle_events_id"), table_name="truffle_events")
    op.drop_table("truffle_events")

    op.drop_index("ix_plant_user_plot", table_name="plants")
    op.drop_index(op.f("ix_plants_user_id"), table_name="plants")
    op.drop_index(op.f("ix_plants_plot_id"), table_name="plants")
    op.drop_index(op.f("ix_plants_id"), table_name="plants")
    op.drop_table("plants")
