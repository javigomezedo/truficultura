"""add_rainfall_records

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rainfall_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plot_id", sa.Integer(), nullable=True),
        sa.Column("municipio_cod", sa.String(length=10), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("precipitation_mm", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "source", sa.String(length=20), nullable=False, server_default="manual"
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_rainfall_records_id"), "rainfall_records", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_rainfall_records_user_id"),
        "rainfall_records",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rainfall_records_plot_id"),
        "rainfall_records",
        ["plot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rainfall_records_municipio_cod"),
        "rainfall_records",
        ["municipio_cod"],
        unique=False,
    )
    op.create_index(
        op.f("ix_rainfall_records_date"), "rainfall_records", ["date"], unique=False
    )
    op.create_index(
        op.f("ix_rainfall_records_source"), "rainfall_records", ["source"], unique=False
    )
    op.create_index(
        "ix_rainfall_user_date",
        "rainfall_records",
        ["user_id", "date"],
        unique=False,
    )
    op.create_index(
        "ix_rainfall_user_plot_date",
        "rainfall_records",
        ["user_id", "plot_id", "date"],
        unique=False,
    )
    op.create_index(
        "ix_rainfall_user_municipio_date",
        "rainfall_records",
        ["user_id", "municipio_cod", "date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_rainfall_user_municipio_date", table_name="rainfall_records")
    op.drop_index("ix_rainfall_user_plot_date", table_name="rainfall_records")
    op.drop_index("ix_rainfall_user_date", table_name="rainfall_records")
    op.drop_index(op.f("ix_rainfall_records_source"), table_name="rainfall_records")
    op.drop_index(op.f("ix_rainfall_records_date"), table_name="rainfall_records")
    op.drop_index(
        op.f("ix_rainfall_records_municipio_cod"), table_name="rainfall_records"
    )
    op.drop_index(op.f("ix_rainfall_records_plot_id"), table_name="rainfall_records")
    op.drop_index(op.f("ix_rainfall_records_user_id"), table_name="rainfall_records")
    op.drop_index(op.f("ix_rainfall_records_id"), table_name="rainfall_records")
    op.drop_table("rainfall_records")
