"""add_recurring_expenses

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recurring_expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("plot_id", sa.Integer(), nullable=True),
        sa.Column("person", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("frequency", sa.String(length=20), nullable=False, server_default="monthly"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recurring_expenses_id"), "recurring_expenses", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_recurring_expenses_user_id"),
        "recurring_expenses",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recurring_expenses_plot_id"),
        "recurring_expenses",
        ["plot_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_recurring_expenses_plot_id"), table_name="recurring_expenses"
    )
    op.drop_index(
        op.f("ix_recurring_expenses_user_id"), table_name="recurring_expenses"
    )
    op.drop_index(op.f("ix_recurring_expenses_id"), table_name="recurring_expenses")
    op.drop_table("recurring_expenses")
