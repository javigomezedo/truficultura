"""change float columns to numeric for monetary precision

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-05
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0028"
down_revision: str = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # expenses.amount: FLOAT -> NUMERIC(12, 2)
    op.alter_column(
        "expenses",
        "amount",
        existing_type=sa.Float(),
        type_=sa.Numeric(12, 2),
        postgresql_using="amount::NUMERIC(12, 2)",
    )

    # incomes.amount_kg: FLOAT -> NUMERIC(10, 3)
    op.alter_column(
        "incomes",
        "amount_kg",
        existing_type=sa.Float(),
        type_=sa.Numeric(10, 3),
        postgresql_using="amount_kg::NUMERIC(10, 3)",
    )

    # incomes.euros_per_kg: FLOAT -> NUMERIC(10, 4)
    op.alter_column(
        "incomes",
        "euros_per_kg",
        existing_type=sa.Float(),
        type_=sa.Numeric(10, 4),
        postgresql_using="euros_per_kg::NUMERIC(10, 4)",
    )

    # plots.area_ha: FLOAT -> NUMERIC(10, 4)
    op.alter_column(
        "plots",
        "area_ha",
        existing_type=sa.Float(),
        type_=sa.Numeric(10, 4),
        existing_nullable=True,
        postgresql_using="area_ha::NUMERIC(10, 4)",
    )

    # plots.percentage: FLOAT -> NUMERIC(7, 4)
    op.alter_column(
        "plots",
        "percentage",
        existing_type=sa.Float(),
        type_=sa.Numeric(7, 4),
        postgresql_using="percentage::NUMERIC(7, 4)",
    )

    # plots.caudal_riego: FLOAT -> NUMERIC(10, 4)
    op.alter_column(
        "plots",
        "caudal_riego",
        existing_type=sa.Float(),
        type_=sa.Numeric(10, 4),
        existing_nullable=True,
        postgresql_using="caudal_riego::NUMERIC(10, 4)",
    )


def downgrade() -> None:
    op.alter_column(
        "plots",
        "caudal_riego",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="caudal_riego::FLOAT",
    )
    op.alter_column(
        "plots",
        "percentage",
        existing_type=sa.Numeric(7, 4),
        type_=sa.Float(),
        postgresql_using="percentage::FLOAT",
    )
    op.alter_column(
        "plots",
        "area_ha",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="area_ha::FLOAT",
    )
    op.alter_column(
        "incomes",
        "euros_per_kg",
        existing_type=sa.Numeric(10, 4),
        type_=sa.Float(),
        postgresql_using="euros_per_kg::FLOAT",
    )
    op.alter_column(
        "incomes",
        "amount_kg",
        existing_type=sa.Numeric(10, 3),
        type_=sa.Float(),
        postgresql_using="amount_kg::FLOAT",
    )
    op.alter_column(
        "expenses",
        "amount",
        existing_type=sa.Numeric(12, 2),
        type_=sa.Float(),
        postgresql_using="amount::FLOAT",
    )
