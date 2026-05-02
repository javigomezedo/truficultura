from __future__ import annotations

import datetime
import secrets
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, TenantInvitation, TenantMembership
from app.models.user import User

_INVITATION_TTL_DAYS = 7


async def _get_invitation_by_token(
    db: AsyncSession, token: str
) -> Optional[TenantInvitation]:
    res = await db.execute(
        select(TenantInvitation).where(TenantInvitation.token == token)
    )
    return res.scalar_one_or_none()


async def create_invitation(
    db: AsyncSession,
    *,
    tenant_id: int,
    email: str,
    invited_by_user_id: int,
    role: str = "member",
) -> TenantInvitation:
    """Crea una invitación para unirse al tenant. Si ya existe una pendiente para ese
    email en el mismo tenant, la reutiliza (renovando la fecha de expiración)."""
    email = email.strip().lower()

    # Verificar que el email no sea ya un miembro
    user_res = await db.execute(select(User).where(User.email == email))
    user = user_res.scalar_one_or_none()
    if user is not None:
        membership_res = await db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user.id,
            )
        )
        if membership_res.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ese email ya es miembro de este tenant",
            )

    # Reutilizar invitación pendiente si existe
    existing_res = await db.execute(
        select(TenantInvitation).where(
            TenantInvitation.tenant_id == tenant_id,
            TenantInvitation.email == email,
            TenantInvitation.accepted_at.is_(None),
        )
    )
    existing = existing_res.scalar_one_or_none()

    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        days=_INVITATION_TTL_DAYS
    )

    if existing is not None:
        existing.token = secrets.token_urlsafe(32)
        existing.expires_at = expires_at
        existing.invited_by_user_id = invited_by_user_id
        existing.role = role
        await db.flush()
        return existing

    invitation = TenantInvitation(
        tenant_id=tenant_id,
        email=email,
        token=secrets.token_urlsafe(32),
        invited_by_user_id=invited_by_user_id,
        role=role,
        expires_at=expires_at,
    )
    db.add(invitation)
    await db.flush()
    return invitation


async def list_pending_invitations(
    db: AsyncSession, tenant_id: int
) -> list[TenantInvitation]:
    """Devuelve invitaciones pendientes (no aceptadas y no expiradas)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    res = await db.execute(
        select(TenantInvitation)
        .where(
            TenantInvitation.tenant_id == tenant_id,
            TenantInvitation.accepted_at.is_(None),
            TenantInvitation.expires_at > now,
        )
        .order_by(TenantInvitation.created_at.desc())
    )
    return res.scalars().all()


async def revoke_invitation(
    db: AsyncSession,
    *,
    invitation_id: int,
    tenant_id: int,
) -> None:
    """Revoca una invitación pendiente."""
    res = await db.execute(
        select(TenantInvitation).where(
            TenantInvitation.id == invitation_id,
            TenantInvitation.tenant_id == tenant_id,
        )
    )
    invitation = res.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitación no encontrada"
        )
    await db.delete(invitation)
    await db.flush()


async def get_invitation_for_token(
    db: AsyncSession, token: str
) -> Optional[TenantInvitation]:
    """Devuelve la invitación si el token es válido y no ha expirado ni sido aceptada."""
    now = datetime.datetime.now(datetime.timezone.utc)
    invitation = await _get_invitation_by_token(db, token)
    if invitation is None:
        return None
    if invitation.accepted_at is not None:
        return None
    if invitation.expires_at < now:
        return None
    return invitation


async def accept_invitation(
    db: AsyncSession,
    *,
    token: str,
    user_id: int,
) -> TenantMembership:
    """Acepta la invitación y crea el TenantMembership. Idempotente si ya es miembro."""
    invitation = await get_invitation_for_token(db, token)
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La invitación no es válida o ha expirado",
        )

    # Verificar que la invitación fue enviada al email del usuario que intenta aceptarla.
    # Esto impide que un usuario distinto al destinatario original pueda unirse al
    # tenant aunque haya obtenido el token de alguna manera.
    user_res = await db.execute(select(User).where(User.id == user_id))
    user = user_res.scalar_one_or_none()
    if user is None or user.email.lower() != invitation.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta invitación no corresponde a tu cuenta",
        )

    # Verificar si ya es miembro del tenant destino (idempotente)
    existing_res = await db.execute(
        select(TenantMembership).where(
            TenantMembership.tenant_id == invitation.tenant_id,
            TenantMembership.user_id == user_id,
        )
    )
    existing_membership = existing_res.scalar_one_or_none()
    if existing_membership is not None:
        # Marcar aceptada de todos modos y devolver la membresía existente
        invitation.accepted_at = datetime.datetime.now(datetime.timezone.utc)
        await db.flush()
        return existing_membership

    # Eliminar la membresía previa del usuario en cualquier otro tenant (solo-tenant
    # creado al registrarse). Un usuario sólo puede pertenecer a un tenant a la vez.
    previous_res = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id != invitation.tenant_id,
        )
    )
    old_memberships = previous_res.scalars().all()
    old_tenant_ids = [m.tenant_id for m in old_memberships]
    for old_membership in old_memberships:
        await db.delete(old_membership)
    await db.flush()

    # Eliminar los tenants que quedaron huérfanos (sin miembros y sin Stripe).
    # Ocurre siempre con el solo-tenant personal creado al registrarse.
    for old_tenant_id in old_tenant_ids:
        remaining_res = await db.execute(
            select(TenantMembership).where(TenantMembership.tenant_id == old_tenant_id)
        )
        if remaining_res.scalar_one_or_none() is None:
            tenant_res = await db.execute(
                select(Tenant).where(Tenant.id == old_tenant_id)
            )
            orphaned = tenant_res.scalar_one_or_none()
            if orphaned is not None and orphaned.stripe_customer_id is None:
                await db.delete(orphaned)

    membership = TenantMembership(
        tenant_id=invitation.tenant_id,
        user_id=user_id,
        role=invitation.role,
        invited_by_user_id=invitation.invited_by_user_id,
    )
    db.add(membership)

    invitation.accepted_at = datetime.datetime.now(datetime.timezone.utc)
    await db.flush()
    return membership
