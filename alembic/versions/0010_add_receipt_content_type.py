"""Add receipt_content_type to expenses.

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-31 00:01:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("receipt_content_type", sa.String(length=100), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.drop_column("receipt_content_type")
