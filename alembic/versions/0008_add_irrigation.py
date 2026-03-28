"""Add irrigation support: has_irrigation flag on plots and irrigation_records table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-28 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add has_irrigation column to plots
    with op.batch_alter_table("plots", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "has_irrigation",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # Create irrigation_records table
    op.create_table(
        "irrigation_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("plot_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("water_m3", sa.Float(), nullable=False),
        sa.Column("expense_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_irrigation_records_id"), "irrigation_records", ["id"])
    op.create_index(
        op.f("ix_irrigation_records_user_id"), "irrigation_records", ["user_id"]
    )
    op.create_index(
        op.f("ix_irrigation_records_plot_id"), "irrigation_records", ["plot_id"]
    )
    op.create_index(op.f("ix_irrigation_records_date"), "irrigation_records", ["date"])
    op.create_index(
        op.f("ix_irrigation_records_expense_id"), "irrigation_records", ["expense_id"]
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_irrigation_records_expense_id"), table_name="irrigation_records"
    )
    op.drop_index(op.f("ix_irrigation_records_date"), table_name="irrigation_records")
    op.drop_index(
        op.f("ix_irrigation_records_plot_id"), table_name="irrigation_records"
    )
    op.drop_index(
        op.f("ix_irrigation_records_user_id"), table_name="irrigation_records"
    )
    op.drop_index(op.f("ix_irrigation_records_id"), table_name="irrigation_records")
    op.drop_table("irrigation_records")

    with op.batch_alter_table("plots", schema=None) as batch_op:
        batch_op.drop_column("has_irrigation")
