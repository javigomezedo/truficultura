from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tenant import Tenant, TenantMembership
from app.models.user import User


async def _create_solo_tenant(db: AsyncSession, user: User) -> TenantMembership:
    """Crea un tenant personal para el usuario y lo vincula como owner.
    Se usa cuando un usuario es expulsado de un tenant compartido y queda sin tenant.
    """
    full_name = f"{user.first_name} {user.last_name}".strip() or user.username
    base_slug = re.sub(r"[^\w\s-]", "", full_name.lower()).strip()
    base_slug = re.sub(r"[\s_]+", "-", base_slug) or f"user-{user.id}"

    slug = base_slug
    counter = 1
    while True:
        exists = await db.execute(select(Tenant).where(Tenant.slug == slug))
        if not exists.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    new_tenant = Tenant(name=full_name, slug=slug)
    db.add(new_tenant)
    await db.flush()

    membership = TenantMembership(
        tenant_id=new_tenant.id,
        user_id=user.id,
        role="owner",
    )
    db.add(membership)
    await db.flush()
    return membership


async def get_tenant(db: AsyncSession, tenant_id: int) -> Optional[Tenant]:
    """Devuelve el tenant o None."""
    res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    return res.scalar_one_or_none()


async def update_tenant(
    db: AsyncSession,
    *,
    tenant_id: int,
    name: str,
    acting_user_id: Optional[int] = None,
) -> Tenant:
    """Actualiza el nombre del tenant. Requiere que exista."""
    tenant = await get_tenant(db, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant no encontrado"
        )

    tenant.name = name.strip()
    await db.flush()
    return tenant


async def list_members(db: AsyncSession, tenant_id: int) -> list[TenantMembership]:
    """Devuelve los miembros del tenant con el objeto User cargado."""
    res = await db.execute(
        select(TenantMembership)
        .options(selectinload(TenantMembership.user))
        .where(TenantMembership.tenant_id == tenant_id)
        .order_by(TenantMembership.joined_at)
    )
    return res.scalars().all()


async def get_membership(
    db: AsyncSession, tenant_id: int, user_id: int
) -> Optional[TenantMembership]:
    res = await db.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    )
    return res.scalar_one_or_none()


async def change_member_role(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    new_role: str,
    acting_user_id: Optional[int] = None,
) -> TenantMembership:
    """Cambia el rol de un miembro. No permite tocar al owner."""
    membership = await get_membership(db, tenant_id, user_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Miembro no encontrado"
        )
    if membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede cambiar el rol del propietario",
        )
    if new_role not in ("admin", "member"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rol no válido. Usa 'admin' o 'member'",
        )
    membership.role = new_role
    await db.flush()
    return membership


async def remove_member(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    acting_user_id: Optional[int] = None,
) -> None:
    """Elimina a un miembro del tenant. No permite eliminar al owner.
    Tras la expulsión crea un tenant personal para el usuario expulsado,
    de modo que nunca quede sin tenant activo.
    """
    membership = await get_membership(db, tenant_id, user_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Miembro no encontrado"
        )
    if membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar al propietario del tenant",
        )
    await db.delete(membership)
    await db.flush()

    # Recrear un tenant personal para el usuario expulsado para que no quede
    # sin tenant activo y pueda seguir usando la aplicación.
    user_res = await db.execute(select(User).where(User.id == user_id))
    user = user_res.scalar_one_or_none()
    if user is not None:
        await _create_solo_tenant(db, user)
