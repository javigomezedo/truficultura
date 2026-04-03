"""Rename num_holm_oaks to num_plants for consistency and flexibility.

Revision ID: 0007
Revises: 0006
Create Date: 2025-03-25 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename the column
    with op.batch_alter_table("plots", schema=None) as batch_op:
        batch_op.alter_column("num_holm_oaks", new_column_name="num_plants")


def downgrade() -> None:
    # Rename back to the original column name
    with op.batch_alter_table("plots", schema=None) as batch_op:
        batch_op.alter_column("num_plants", new_column_name="num_holm_oaks")
