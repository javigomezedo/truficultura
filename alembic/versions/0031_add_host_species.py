"""add host species to plants and plots

Revision ID: 0031
Revises: 0030
Create Date: 2025-07-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type (shared by both tables)
    host_species_enum = sa.Enum(
        "encina",
        "roble",
        "quejigo",
        "coscoja",
        "avellano",
        "carpe",
        "otros",
        name="host_species_enum",
    )
    host_species_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "plants",
        sa.Column(
            "host_species",
            sa.Enum(
                "encina",
                "roble",
                "quejigo",
                "coscoja",
                "avellano",
                "carpe",
                "otros",
                name="host_species_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "plots",
        sa.Column(
            "default_host_species",
            sa.Enum(
                "encina",
                "roble",
                "quejigo",
                "coscoja",
                "avellano",
                "carpe",
                "otros",
                name="host_species_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("plots", "default_host_species")
    op.drop_column("plants", "host_species")
    sa.Enum(name="host_species_enum").drop(op.get_bind(), checkfirst=True)
