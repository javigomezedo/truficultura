"""Integration tests for multi-tenant lifecycle (Phase C).

C1 — test_migration_like_flow:
    Simula la migración 0021: crea usuarios directamente en BD, construye tenants
    y memberships, asigna datos, y verifica que no hay huérfanos.

C2 — test_full_tenant_lifecycle:
    Recorre el ciclo completo: invitar, aceptar, cambiar rol, expulsar y verificar
    que el usuario expulsado recibe un nuevo solo-tenant.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base

# Importar todos los modelos para que Base.metadata los registre antes de create_all
from app.models import (  # noqa: F401
    Expense,
    Income,
    Plant,
    Plot,
    Tenant,
    TenantInvitation,
    TenantMembership,
    User,
    Well,
)
from app.services.invitation_service import (
    accept_invitation,
    create_invitation,
    list_pending_invitations,
    revoke_invitation,
)
from app.services.plots_service import create_plot
from app.services.tenant_service import change_member_role, list_members, remove_member


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_sessionmaker(db_file: Path) -> tuple:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_maker


def _make_user(
    username: str,
    email: str,
    first_name: str = "Test",
    last_name: str = "User",
) -> User:
    return User(
        username=username,
        email=email,
        hashed_password="hashed",
        first_name=first_name,
        last_name=last_name,
        role="user",
        is_active=True,
    )


def _make_tenant(name: str, slug: str) -> Tenant:
    return Tenant(name=name, slug=slug)


# ---------------------------------------------------------------------------
# C1 — migration-like flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_like_flow(tmp_path: Path) -> None:
    """Simula la migración 0021: un tenant personal por usuario, datos asignados,
    sin huérfanos al final."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "migration.sqlite3")

    try:
        async with session_maker() as db:
            # --- Crear 2 usuarios ---
            user_a = _make_user("usuario_a", "a@example.com", "Ana", "García")
            user_b = _make_user("usuario_b", "b@example.com", "Bruno", "López")
            db.add_all([user_a, user_b])
            await db.flush()

            # --- Crear un tenant personal para cada usuario (como hace 0021) ---
            tenant_a = _make_tenant("Ana García", "ana-garcia")
            tenant_b = _make_tenant("Bruno López", "bruno-lopez")
            db.add_all([tenant_a, tenant_b])
            await db.flush()

            membership_a = TenantMembership(
                tenant_id=tenant_a.id, user_id=user_a.id, role="owner"
            )
            membership_b = TenantMembership(
                tenant_id=tenant_b.id, user_id=user_b.id, role="owner"
            )
            db.add_all([membership_a, membership_b])
            await db.flush()

            # --- Crear parcelas asociadas al tenant de cada usuario ---
            plot_a = await create_plot(
                db,
                tenant_id=tenant_a.id,
                name="Parcela A1",
                polygon="1",
                plot_num="1",
                cadastral_ref="44223A021001200000AA",
                hydrant="H1",
                sector="S1",
                num_plants=100,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=3.0,
                production_start=datetime.date(2023, 1, 1),
            )
            plot_b = await create_plot(
                db,
                tenant_id=tenant_b.id,
                name="Parcela B1",
                polygon="2",
                plot_num="2",
                cadastral_ref="44223A021001200000BB",
                hydrant="H2",
                sector="S2",
                num_plants=50,
                planting_date=datetime.date(2021, 1, 1),
                area_ha=1.5,
                production_start=datetime.date(2024, 1, 1),
            )
            await db.commit()

            # --- Verificaciones post-migración ---

            # Total de tenants == total de usuarios
            tenants_res = await db.execute(select(Tenant))
            tenants = tenants_res.scalars().all()
            assert len(tenants) == 2

            # Total de memberships == total de usuarios, todos owner
            memberships_res = await db.execute(select(TenantMembership))
            memberships = memberships_res.scalars().all()
            assert len(memberships) == 2
            assert all(m.role == "owner" for m in memberships)

            # Slugs únicos
            slugs = [t.slug for t in tenants]
            assert len(slugs) == len(set(slugs))

            # Cada parcela tiene su tenant correcto — sin huérfanos (tenant_id NOT NULL)
            plots_res = await db.execute(select(Plot))
            plots = plots_res.scalars().all()
            assert len(plots) == 2
            tenant_ids = {p.tenant_id for p in plots}
            assert None not in tenant_ids
            assert plot_a.tenant_id == tenant_a.id
            assert plot_b.tenant_id == tenant_b.id

            # Aislamiento: la parcela de A no aparece en el tenant de B
            plots_b_res = await db.execute(
                select(Plot).where(Plot.tenant_id == tenant_b.id)
            )
            plots_b = plots_b_res.scalars().all()
            assert len(plots_b) == 1
            assert plots_b[0].name == "Parcela B1"

    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# C2 — full tenant lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_tenant_lifecycle(tmp_path: Path) -> None:
    """Ciclo completo: invitar → aceptar → solo-tenant de B eliminado →
    cambiar rol → expulsar → solo-tenant de B recreado."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "lifecycle.sqlite3")

    try:
        async with session_maker() as db:
            # --- Crear usuarios A y B ---
            user_a = _make_user("owner_a", "owner@example.com", "Alma", "Ruiz")
            user_b = _make_user("member_b", "member@example.com", "Blas", "Vera")
            db.add_all([user_a, user_b])
            await db.flush()

            # --- Solo-tenants iniciales ---
            tenant_a = _make_tenant("Alma Ruiz", "alma-ruiz")
            tenant_b = _make_tenant("Blas Vera", "blas-vera")
            db.add_all([tenant_a, tenant_b])
            await db.flush()

            db.add(
                TenantMembership(tenant_id=tenant_a.id, user_id=user_a.id, role="owner")
            )
            db.add(
                TenantMembership(tenant_id=tenant_b.id, user_id=user_b.id, role="owner")
            )
            await db.commit()

            tenant_a_id = tenant_a.id
            tenant_b_id = tenant_b.id

            # --- A invita a B ---
            invitation = await create_invitation(
                db,
                tenant_id=tenant_a_id,
                email=user_b.email,
                invited_by_user_id=user_a.id,
                role="member",
            )
            await db.commit()

            pending = await list_pending_invitations(db, tenant_id=tenant_a_id)
            assert len(pending) == 1
            assert pending[0].email == user_b.email

            # --- B acepta la invitación ---
            membership = await accept_invitation(
                db, token=invitation.token, user_id=user_b.id
            )
            await db.commit()

            assert membership.tenant_id == tenant_a_id
            assert membership.user_id == user_b.id
            assert membership.role == "member"

            # El solo-tenant de B fue eliminado (sin Stripe → huérfano → borrado)
            deleted_tenant_res = await db.execute(
                select(Tenant).where(Tenant.id == tenant_b_id)
            )
            assert deleted_tenant_res.scalar_one_or_none() is None

            # Ahora A tiene 2 miembros: owner A + member B
            members = await list_members(db, tenant_id=tenant_a_id)
            assert len(members) == 2
            roles = {m.user_id: m.role for m in members}
            assert roles[user_a.id] == "owner"
            assert roles[user_b.id] == "member"

            # Invitación marcada como aceptada → pendientes = 0
            pending_after = await list_pending_invitations(db, tenant_id=tenant_a_id)
            assert len(pending_after) == 0

            # --- Cambiar rol de B: member → admin ---
            updated = await change_member_role(
                db,
                tenant_id=tenant_a_id,
                user_id=user_b.id,
                new_role="admin",
            )
            await db.commit()

            assert updated.role == "admin"

            # No se puede cambiar el rol del owner
            import pytest as _pytest
            from fastapi import HTTPException

            with _pytest.raises(HTTPException) as exc_info:
                await change_member_role(
                    db,
                    tenant_id=tenant_a_id,
                    user_id=user_a.id,
                    new_role="member",
                )
            assert exc_info.value.status_code == 400

            # --- A expulsa a B ---
            await remove_member(db, tenant_id=tenant_a_id, user_id=user_b.id)
            await db.commit()

            # B solo tiene un membership → su nuevo solo-tenant
            memberships_b_res = await db.execute(
                select(TenantMembership).where(TenantMembership.user_id == user_b.id)
            )
            memberships_b = memberships_b_res.scalars().all()
            assert len(memberships_b) == 1
            assert memberships_b[0].role == "owner"
            new_tenant_id = memberships_b[0].tenant_id
            assert new_tenant_id != tenant_a_id  # es un tenant nuevo, no el de A

            # El nuevo solo-tenant existe en BD
            new_tenant_res = await db.execute(
                select(Tenant).where(Tenant.id == new_tenant_id)
            )
            new_tenant = new_tenant_res.scalar_one_or_none()
            assert new_tenant is not None

            # A sigue siendo solo owner de su tenant, con un único miembro
            members_after = await list_members(db, tenant_id=tenant_a_id)
            assert len(members_after) == 1
            assert members_after[0].user_id == user_a.id

            # --- Revocar una invitación pendiente ---
            new_inv = await create_invitation(
                db,
                tenant_id=tenant_a_id,
                email="fantasma@prueba.com",
                invited_by_user_id=user_a.id,
            )
            await db.commit()

            await revoke_invitation(db, invitation_id=new_inv.id, tenant_id=tenant_a_id)
            await db.commit()

            pending_final = await list_pending_invitations(db, tenant_id=tenant_a_id)
            assert len(pending_final) == 0

    finally:
        await engine.dispose()
