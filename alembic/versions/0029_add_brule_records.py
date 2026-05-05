"""add brule_records table

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0029"
down_revision: str = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brule_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("plot_id", sa.Integer(), nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("diameter_cm", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plant_id", "record_date", name="uq_brule_per_plant_per_day"
        ),
    )
    op.create_index("ix_brule_records_id", "brule_records", ["id"], unique=False)
    op.create_index(
        "ix_brule_records_tenant_id", "brule_records", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_brule_records_plot_id", "brule_records", ["plot_id"], unique=False
    )
    op.create_index(
        "ix_brule_records_plant_id", "brule_records", ["plant_id"], unique=False
    )
    op.create_index(
        "ix_brule_records_record_date", "brule_records", ["record_date"], unique=False
    )
    op.create_index(
        "ix_brule_tenant_plot", "brule_records", ["tenant_id", "plot_id"], unique=False
    )
    op.create_index(
        "ix_brule_tenant_plot_date",
        "brule_records",
        ["tenant_id", "plot_id", "record_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_brule_tenant_plot_date", table_name="brule_records")
    op.drop_index("ix_brule_tenant_plot", table_name="brule_records")
    op.drop_index("ix_brule_records_record_date", table_name="brule_records")
    op.drop_index("ix_brule_records_plant_id", table_name="brule_records")
    op.drop_index("ix_brule_records_plot_id", table_name="brule_records")
    op.drop_index("ix_brule_records_tenant_id", table_name="brule_records")
    op.drop_index("ix_brule_records_id", table_name="brule_records")
    op.drop_table("brule_records")
