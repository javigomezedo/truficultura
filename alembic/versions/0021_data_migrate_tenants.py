"""data migration: create tenant per user, assign tenant_id to all data tables

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-28

"""

from typing import Sequence, Union

import re

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, Sequence[str], None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slugify(name: str) -> str:
    """Simple slug generator: lowercase, replace spaces and special chars with '-'."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "tenant"


def upgrade() -> None:
    conn = op.get_bind()

    # Tablas de datos que tienen user_id (para asignarles tenant_id)
    data_tables_with_user_id = [
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
    # rainfall_records tiene user_id nullable (NULL = compartido por AEMET/ibericam)
    rainfall_with_user_id = "rainfall_records"

    # Obtener todos los usuarios
    users = conn.execute(
        sa.text(
            "SELECT id, first_name, last_name, username, "
            "stripe_customer_id, subscription_status, trial_ends_at, subscription_ends_at "
            "FROM users ORDER BY id"
        )
    ).fetchall()

    used_slugs: set[str] = set()

    for user in users:
        user_id = user[0]
        first_name = user[1] or ""
        last_name = user[2] or ""
        username = user[3] or ""
        stripe_customer_id = user[4]
        subscription_status = user[5] or "trialing"
        trial_ends_at = user[6]
        subscription_ends_at = user[7]

        # Generar nombre y slug del tenant
        full_name = f"{first_name} {last_name}".strip() or username
        base_slug = _slugify(full_name) or f"user-{user_id}"

        # Garantizar slug único
        slug = base_slug
        counter = 1
        while slug in used_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1
        used_slugs.add(slug)

        # Crear tenant
        result = conn.execute(
            sa.text(
                "INSERT INTO tenants "
                "(name, slug, stripe_customer_id, subscription_status, trial_ends_at, subscription_ends_at) "
                "VALUES (:name, :slug, :stripe_customer_id, :subscription_status, :trial_ends_at, :subscription_ends_at) "
                "RETURNING id"
            ),
            {
                "name": full_name,
                "slug": slug,
                "stripe_customer_id": stripe_customer_id,
                "subscription_status": subscription_status,
                "trial_ends_at": trial_ends_at,
                "subscription_ends_at": subscription_ends_at,
            },
        )
        tenant_id = result.fetchone()[0]

        # Crear membership como owner
        conn.execute(
            sa.text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:tenant_id, :user_id, 'owner')"
            ),
            {"tenant_id": tenant_id, "user_id": user_id},
        )

        # Asignar tenant_id y created_by_user_id a todas las tablas de datos
        for table in data_tables_with_user_id:
            conn.execute(
                sa.text(
                    f"UPDATE {table} "
                    "SET tenant_id = :tenant_id, created_by_user_id = user_id "
                    "WHERE user_id = :user_id"
                ),
                {"tenant_id": tenant_id, "user_id": user_id},
            )

        # rainfall_records: solo los que tienen user_id (registros manuales)
        conn.execute(
            sa.text(
                "UPDATE rainfall_records "
                "SET tenant_id = :tenant_id, created_by_user_id = user_id "
                "WHERE user_id = :user_id"
            ),
            {"tenant_id": tenant_id, "user_id": user_id},
        )


def downgrade() -> None:
    """Downgrade limpia tenant_id y created_by_user_id, y borra las memberships/tenants.

    Los datos de billing (stripe_customer_id, etc.) en tenants se perderán —
    deberían restaurarse desde un backup antes de ejecutar este downgrade en producción.
    """
    conn = op.get_bind()

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
        conn.execute(
            sa.text(f"UPDATE {table} SET tenant_id = NULL, created_by_user_id = NULL")
        )

    conn.execute(sa.text("DELETE FROM tenant_memberships"))
    conn.execute(sa.text("DELETE FROM tenant_invitations"))
    conn.execute(sa.text("DELETE FROM tenants"))
