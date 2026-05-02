"""add tenants, tenant_memberships, tenant_invitations; add tenant_id and audit columns

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, Sequence[str], None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Nuevas tablas ──────────────────────────────────────────────────────

    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
        sa.Column(
            "subscription_status",
            sa.String(30),
            server_default="trialing",
            nullable=False,
        ),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenants_id"), "tenants", ["id"])
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=True)
    op.create_index(
        op.f("ix_tenants_stripe_customer_id"),
        "tenants",
        ["stripe_customer_id"],
        unique=True,
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
    )
    op.create_index(op.f("ix_tenant_memberships_id"), "tenant_memberships", ["id"])
    op.create_index("ix_tenant_membership_user", "tenant_memberships", ["user_id"])
    op.create_index("ix_tenant_membership_tenant", "tenant_memberships", ["tenant_id"])

    op.create_table(
        "tenant_invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_invitations_id"), "tenant_invitations", ["id"])
    op.create_index(
        op.f("ix_tenant_invitations_token"),
        "tenant_invitations",
        ["token"],
        unique=True,
    )
    op.create_index("ix_tenant_invitation_tenant", "tenant_invitations", ["tenant_id"])

    # ── 2. Columnas tenant_id / created_by_user_id / updated_by_user_id ──────
    # Todas nullable inicialmente; la migración 0018 (data) las rellena,
    # y la 0019 pone NOT NULL donde corresponda.

    for table in [
        "plots",
        "expenses",
        "incomes",
        "plants",
        "truffle_events",
        "irrigation_records",
        "wells",
        "plot_events",
        "recurring_expenses",
        "rainfall_records",
        "plot_harvests",
        "plant_presences",
        "expense_proration_groups",
    ]:
        op.add_column(
            table,
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=True,
                index=True,
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
        )

    # updated_by_user_id solo para modelos mutables
    for table in [
        "plots",
        "expenses",
        "incomes",
        "plants",
        "irrigation_records",
        "wells",
        "plot_events",
        "recurring_expenses",
        "rainfall_records",
        "plot_harvests",
        "expense_proration_groups",
    ]:
        op.add_column(
            table,
            sa.Column(
                "updated_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    # ── 3. Nuevos índices compuestos (reemplazan los de user_id) ─────────────
    op.create_index("ix_plant_tenant_plot", "plants", ["tenant_id", "plot_id"])
    op.create_index(
        "ix_plant_tenant_plot_visual", "plants", ["tenant_id", "plot_id", "visual_col"]
    )
    op.create_index(
        "ix_truffle_event_tenant_plot_plant",
        "truffle_events",
        ["tenant_id", "plot_id", "plant_id"],
    )
    op.create_index(
        "ix_plot_event_tenant_plot_date",
        "plot_events",
        ["tenant_id", "plot_id", "date"],
    )
    op.create_index(
        "ix_plot_event_tenant_plot_type",
        "plot_events",
        ["tenant_id", "plot_id", "event_type"],
    )
    op.create_index(
        "ix_rainfall_tenant_date", "rainfall_records", ["tenant_id", "date"]
    )
    op.create_index(
        "ix_rainfall_tenant_plot_date",
        "rainfall_records",
        ["tenant_id", "plot_id", "date"],
    )
    op.create_index(
        "ix_rainfall_tenant_municipio_date",
        "rainfall_records",
        ["tenant_id", "municipio_cod", "date"],
    )
    op.create_index(
        "ix_plot_harvest_tenant_plot", "plot_harvests", ["tenant_id", "plot_id"]
    )
    op.create_index(
        "ix_plot_harvest_tenant_date", "plot_harvests", ["tenant_id", "harvest_date"]
    )
    op.create_index(
        "ix_plant_presence_tenant_plot", "plant_presences", ["tenant_id", "plot_id"]
    )
    op.create_index(
        "ix_plant_presence_tenant_plot_date",
        "plant_presences",
        ["tenant_id", "plot_id", "presence_date"],
    )


def downgrade() -> None:
    # Eliminar índices de tenant
    for idx in [
        ("plant_presences", "ix_plant_presence_tenant_plot_date"),
        ("plant_presences", "ix_plant_presence_tenant_plot"),
        ("plot_harvests", "ix_plot_harvest_tenant_date"),
        ("plot_harvests", "ix_plot_harvest_tenant_plot"),
        ("rainfall_records", "ix_rainfall_tenant_municipio_date"),
        ("rainfall_records", "ix_rainfall_tenant_plot_date"),
        ("rainfall_records", "ix_rainfall_tenant_date"),
        ("plot_events", "ix_plot_event_tenant_plot_type"),
        ("plot_events", "ix_plot_event_tenant_plot_date"),
        ("truffle_events", "ix_truffle_event_tenant_plot_plant"),
        ("plants", "ix_plant_tenant_plot_visual"),
        ("plants", "ix_plant_tenant_plot"),
    ]:
        op.drop_index(idx[1], table_name=idx[0])

    # Eliminar columnas de auditoría y tenant_id
    for table in [
        "plots",
        "expenses",
        "incomes",
        "plants",
        "irrigation_records",
        "wells",
        "plot_events",
        "recurring_expenses",
        "rainfall_records",
        "plot_harvests",
        "expense_proration_groups",
    ]:
        op.drop_column(table, "updated_by_user_id")

    for table in [
        "plots",
        "expenses",
        "incomes",
        "plants",
        "truffle_events",
        "irrigation_records",
        "wells",
        "plot_events",
        "recurring_expenses",
        "rainfall_records",
        "plot_harvests",
        "plant_presences",
        "expense_proration_groups",
    ]:
        op.drop_column(table, "created_by_user_id")
        op.drop_column(table, "tenant_id")

    # Eliminar tablas de tenant
    op.drop_table("tenant_invitations")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
