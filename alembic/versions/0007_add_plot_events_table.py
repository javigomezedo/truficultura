"""add_plot_events_table

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plot_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plot_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "is_recurring", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("related_irrigation_id", sa.Integer(), nullable=True),
        sa.Column("related_well_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["related_irrigation_id"], ["irrigation_records.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["related_well_id"], ["wells.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "related_irrigation_id", name="uq_plot_events_related_irrigation"
        ),
        sa.UniqueConstraint("related_well_id", name="uq_plot_events_related_well"),
    )

    op.create_index("ix_plot_events_id", "plot_events", ["id"], unique=False)
    op.create_index("ix_plot_events_user_id", "plot_events", ["user_id"], unique=False)
    op.create_index("ix_plot_events_plot_id", "plot_events", ["plot_id"], unique=False)
    op.create_index(
        "ix_plot_events_event_type", "plot_events", ["event_type"], unique=False
    )
    op.create_index("ix_plot_events_date", "plot_events", ["date"], unique=False)
    op.create_index(
        "ix_plot_event_user_plot_date",
        "plot_events",
        ["user_id", "plot_id", "date"],
        unique=False,
    )
    op.create_index(
        "ix_plot_event_user_plot_type",
        "plot_events",
        ["user_id", "plot_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_plot_event_user_plot_type", table_name="plot_events")
    op.drop_index("ix_plot_event_user_plot_date", table_name="plot_events")
    op.drop_index("ix_plot_events_date", table_name="plot_events")
    op.drop_index("ix_plot_events_event_type", table_name="plot_events")
    op.drop_index("ix_plot_events_plot_id", table_name="plot_events")
    op.drop_index("ix_plot_events_user_id", table_name="plot_events")
    op.drop_index("ix_plot_events_id", table_name="plot_events")
    op.drop_table("plot_events")
