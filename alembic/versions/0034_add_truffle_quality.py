"""0034 – Add truffle quality enum to incomes and truffle_events

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-07

Maps legacy letter-based categories in incomes:
  A → extra, B → primera, C → segunda, D → blanda
  agusanada → agusanada
  Any other value → NULL
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

_QUALITY_VALUES = ("extra", "primera", "segunda", "blanda", "agusanada")


def upgrade() -> None:
    # 1. Create the PostgreSQL ENUM type
    trufflequality = sa.Enum(*_QUALITY_VALUES, name="trufflequality")
    trufflequality.create(op.get_bind(), checkfirst=True)

    # 2. Add temporary column on incomes to hold migrated values
    op.add_column(
        "incomes",
        sa.Column(
            "category_new",
            sa.Enum(*_QUALITY_VALUES, name="trufflequality"),
            nullable=True,
        ),
    )

    # 3. Migrate existing data with mapping
    op.execute(
        """
        UPDATE incomes
        SET category_new = CASE
            WHEN LOWER(TRIM(category)) IN ('a', 'extra')    THEN 'extra'::trufflequality
            WHEN LOWER(TRIM(category)) IN ('b', 'primera')  THEN 'primera'::trufflequality
            WHEN LOWER(TRIM(category)) IN ('c', 'segunda')  THEN 'segunda'::trufflequality
            WHEN LOWER(TRIM(category)) IN ('d', 'blanda')   THEN 'blanda'::trufflequality
            WHEN LOWER(TRIM(category)) = 'agusanada'        THEN 'agusanada'::trufflequality
            ELSE NULL
        END
        """
    )

    # 4. Drop the old text column and rename the new one
    op.drop_column("incomes", "category")
    op.alter_column("incomes", "category_new", new_column_name="category")

    # 5. Add quality column to truffle_events
    op.add_column(
        "truffle_events",
        sa.Column(
            "quality", sa.Enum(*_QUALITY_VALUES, name="trufflequality"), nullable=True
        ),
    )


def downgrade() -> None:
    # 1. Remove quality from truffle_events
    op.drop_column("truffle_events", "quality")

    # 2. Restore incomes.category as VARCHAR
    op.add_column(
        "incomes",
        sa.Column("category_old", sa.String(200), nullable=True),
    )
    op.execute(
        """
        UPDATE incomes
        SET category_old = category::text
        WHERE category IS NOT NULL
        """
    )
    op.drop_column("incomes", "category")
    op.alter_column("incomes", "category_old", new_column_name="category")

    # Make category NOT NULL with empty default to restore original constraint
    op.execute("UPDATE incomes SET category = '' WHERE category IS NULL")
    op.alter_column("incomes", "category", nullable=False, server_default="")

    # 3. Drop the ENUM type
    sa.Enum(name="trufflequality").drop(op.get_bind(), checkfirst=True)
