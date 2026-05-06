"""add plant status and baja_date columns

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision: str = "0030"
down_revision: str = "0029"
branch_labels = None
depends_on = None

plant_status_enum = sa.Enum(
    "viva",
    "estresada",
    "muerta",
    "reemplazada",
    name="plant_status_enum",
)


def upgrade() -> None:
    plant_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "plants",
        sa.Column(
            "status",
            plant_status_enum,
            nullable=False,
            server_default="viva",
        ),
    )
    op.add_column(
        "plants",
        sa.Column("baja_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plants", "baja_date")
    op.drop_column("plants", "status")
    plant_status_enum.drop(op.get_bind(), checkfirst=True)
