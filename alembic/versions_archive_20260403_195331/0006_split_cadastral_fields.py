"""Split cadastral_ref into plot_num and cadastral_ref

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename cadastral_ref column to plot_num
    op.alter_column("plots", "cadastral_ref", new_column_name="plot_num")

    # Add new cadastral_ref column for official reference
    op.add_column(
        "plots",
        sa.Column("cadastral_ref", sa.String(100), nullable=False, server_default=""),
    )


def downgrade() -> None:
    # Remove cadastral_ref column
    op.drop_column("plots", "cadastral_ref")

    # Rename plot_num back to cadastral_ref
    op.alter_column("plots", "plot_num", new_column_name="cadastral_ref")
