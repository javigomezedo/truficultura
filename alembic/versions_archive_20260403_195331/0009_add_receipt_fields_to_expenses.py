"""Add receipt fields to expenses: receipt_filename and receipt_data for binary storage.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-31 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add receipt fields to expenses
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("receipt_filename", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(sa.Column("receipt_data", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    # Remove receipt fields from expenses
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.drop_column("receipt_data")
        batch_op.drop_column("receipt_filename")
