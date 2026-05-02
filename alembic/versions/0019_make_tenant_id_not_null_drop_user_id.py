"""make tenant_id NOT NULL, drop user_id from data tables, drop billing from users

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, Sequence[str], None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas donde tenant_id pasa a NOT NULL (todas excepto rainfall_records)
TABLES_NOT_NULL_TENANT = [
    "plots",
    "expenses",
    "incomes",
    "plants",
    "truffle_events",
    "irrigation_records",
    "wells",
    "plot_events",
    "recurring_expenses",
    "plot_harvests",
    "plant_presences",
    "expense_proration_groups",
]

# Todas las tablas de datos que tenían user_id (que hay que eliminar)
ALL_DATA_TABLES = TABLES_NOT_NULL_TENANT + ["rainfall_records"]


def upgrade() -> None:
    # ── 1. Hacer tenant_id NOT NULL (excepto rainfall_records) ───────────────
    for table in TABLES_NOT_NULL_TENANT:
        op.alter_column(table, "tenant_id", nullable=False)

    # ── 2. Eliminar índices viejos basados en user_id ─────────────────────────
    old_indexes = [
        ("plants", "ix_plant_user_plot"),
        ("plants", "ix_plant_user_plot_visual"),
        ("truffle_events", "ix_truffle_event_user_plot_plant"),
        ("plot_events", "ix_plot_event_user_plot_date"),
        ("plot_events", "ix_plot_event_user_plot_type"),
        ("rainfall_records", "ix_rainfall_user_date"),
        ("rainfall_records", "ix_rainfall_user_plot_date"),
        ("rainfall_records", "ix_rainfall_user_municipio_date"),
        ("plot_harvests", "ix_plot_harvest_user_plot"),
        ("plot_harvests", "ix_plot_harvest_user_date"),
        ("plant_presences", "ix_plant_presence_user_plot"),
        ("plant_presences", "ix_plant_presence_user_plot_date"),
    ]
    for table, index_name in old_indexes:
        op.drop_index(index_name, table_name=table)

    # ── 3. Eliminar columna user_id de todas las tablas de datos ─────────────
    for table in ALL_DATA_TABLES:
        op.drop_column(table, "user_id")

    # ── 4. Eliminar campos de billing de users ───────────────────────────────
    op.drop_index("ix_users_stripe_customer_id", table_name="users")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "trial_ends_at")
    op.drop_column("users", "subscription_ends_at")


def downgrade() -> None:
    """Restaura billing en users y user_id en tablas de datos.

    NOTA: los valores reales de billing y user_id se perderán; este downgrade
    solo restaura la estructura. Para datos completos, usar un backup previo.
    """
    # Restaurar columnas de billing en users
    op.add_column(
        "users",
        sa.Column("subscription_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "subscription_status",
            sa.String(30),
            nullable=False,
            server_default="trialing",
        ),
    )
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_users_stripe_customer_id", "users", ["stripe_customer_id"], unique=True
    )

    # Restaurar user_id en tablas de datos
    for table in ALL_DATA_TABLES:
        op.add_column(
            table,
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )

    # Revertir NOT NULL en tenant_id
    for table in TABLES_NOT_NULL_TENANT:
        op.alter_column(table, "tenant_id", nullable=True)

    # Restaurar índices basados en user_id
    op.create_index("ix_plant_user_plot", "plants", ["user_id", "plot_id"])
    op.create_index(
        "ix_plant_user_plot_visual", "plants", ["user_id", "plot_id", "visual_col"]
    )
    op.create_index(
        "ix_truffle_event_user_plot_plant",
        "truffle_events",
        ["user_id", "plot_id", "plant_id"],
    )
    op.create_index(
        "ix_plot_event_user_plot_date", "plot_events", ["user_id", "plot_id", "date"]
    )
    op.create_index(
        "ix_plot_event_user_plot_type",
        "plot_events",
        ["user_id", "plot_id", "event_type"],
    )
    op.create_index("ix_rainfall_user_date", "rainfall_records", ["user_id", "date"])
    op.create_index(
        "ix_rainfall_user_plot_date", "rainfall_records", ["user_id", "plot_id", "date"]
    )
    op.create_index(
        "ix_rainfall_user_municipio_date",
        "rainfall_records",
        ["user_id", "municipio_cod", "date"],
    )
    op.create_index(
        "ix_plot_harvest_user_plot", "plot_harvests", ["user_id", "plot_id"]
    )
    op.create_index(
        "ix_plot_harvest_user_date", "plot_harvests", ["user_id", "harvest_date"]
    )
    op.create_index(
        "ix_plant_presence_user_plot", "plant_presences", ["user_id", "plot_id"]
    )
    op.create_index(
        "ix_plant_presence_user_plot_date",
        "plant_presences",
        ["user_id", "plot_id", "presence_date"],
    )
