"""add expense_proration_groups table and proration_group_id to expenses

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, Sequence[str], None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expense_proration_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("years", sa.Integer(), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expense_proration_groups_id"),
        "expense_proration_groups",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expense_proration_groups_user_id"),
        "expense_proration_groups",
        ["user_id"],
        unique=False,
    )

    op.add_column(
        "expenses",
        sa.Column("proration_group_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_expenses_proration_group_id",
        "expenses",
        "expense_proration_groups",
        ["proration_group_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_expenses_proration_group_id"),
        "expenses",
        ["proration_group_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_expenses_proration_group_id"), table_name="expenses")
    op.drop_constraint("fk_expenses_proration_group_id", "expenses", type_="foreignkey")
    op.drop_column("expenses", "proration_group_id")

    op.drop_index(
        op.f("ix_expense_proration_groups_user_id"),
        table_name="expense_proration_groups",
    )
    op.drop_index(
        op.f("ix_expense_proration_groups_id"),
        table_name="expense_proration_groups",
    )
    op.drop_table("expense_proration_groups")
