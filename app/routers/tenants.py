"""Router de ajustes del tenant: nombre, miembros e invitaciones."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.models.user import User
from app.services import invitation_service, tenant_service
from app.services.email_service import send_email
from app.config import settings

router = APIRouter(prefix="/tenant", tags=["tenant"])
templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Ajustes generales ────────────────────────────────────────────────────────


@router.get("/settings", response_class=HTMLResponse)
async def tenant_settings(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = await tenant_service.get_tenant(db, current_user.active_tenant_id)
    members = await tenant_service.list_members(db, current_user.active_tenant_id)
    invitations = await invitation_service.list_pending_invitations(
        db, current_user.active_tenant_id
    )
    membership = await tenant_service.get_membership(
        db, current_user.active_tenant_id, current_user.id
    )
    return templates.TemplateResponse(
        request,
        "tenant/settings.html",
        {
            "request": request,
            "current_user": current_user,
            "tenant": tenant,
            "members": members,
            "invitations": invitations,
            "membership": membership,
        },
    )


@router.post("/settings", response_class=RedirectResponse)
async def tenant_settings_post(
    request: Request,
    name: str = Form(...),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await tenant_service.get_membership(
        db, current_user.active_tenant_id, current_user.id
    )
    if membership is None or membership.role not in ("owner", "admin"):
        return RedirectResponse("/tenant/settings?error=forbidden", status_code=303)

    await tenant_service.update_tenant(
        db,
        tenant_id=current_user.active_tenant_id,
        name=name,
        acting_user_id=current_user.id,
    )
    await db.commit()
    return RedirectResponse("/tenant/settings?saved=1", status_code=303)


# ── Gestión de miembros ──────────────────────────────────────────────────────


@router.post("/members/{user_id}/role", response_class=RedirectResponse)
async def change_member_role(
    user_id: int,
    request: Request,
    role: str = Form(...),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await tenant_service.get_membership(
        db, current_user.active_tenant_id, current_user.id
    )
    if membership is None or membership.role not in ("owner", "admin"):
        return RedirectResponse("/tenant/settings?error=forbidden", status_code=303)

    try:
        await tenant_service.change_member_role(
            db,
            tenant_id=current_user.active_tenant_id,
            user_id=user_id,
            new_role=role,
            acting_user_id=current_user.id,
        )
    except HTTPException:
        return RedirectResponse("/tenant/settings?error=forbidden", status_code=303)
    await db.commit()
    return RedirectResponse("/tenant/settings?saved=1", status_code=303)


@router.post("/members/{user_id}/remove", response_class=RedirectResponse)
async def remove_member(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await tenant_service.get_membership(
        db, current_user.active_tenant_id, current_user.id
    )
    if membership is None or membership.role not in ("owner", "admin"):
        return RedirectResponse("/tenant/settings?error=forbidden", status_code=303)

    try:
        await tenant_service.remove_member(
            db,
            tenant_id=current_user.active_tenant_id,
            user_id=user_id,
            acting_user_id=current_user.id,
        )
    except HTTPException:
        return RedirectResponse("/tenant/settings?error=forbidden", status_code=303)
    await db.commit()
    return RedirectResponse("/tenant/settings?saved=1", status_code=303)


# ── Invitaciones ─────────────────────────────────────────────────────────────


@router.post("/invitations/send", response_class=RedirectResponse)
async def send_invitation(
    request: Request,
    email: str = Form(...),
    role: str = Form("member"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await tenant_service.get_membership(
        db, current_user.active_tenant_id, current_user.id
    )
    if membership is None or membership.role not in ("owner", "admin"):
        return RedirectResponse("/tenant/settings?error=forbidden", status_code=303)

    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        return RedirectResponse("/tenant/settings?error=invalid_email", status_code=303)

    try:
        invitation = await invitation_service.create_invitation(
            db,
            tenant_id=current_user.active_tenant_id,
            email=email,
            invited_by_user_id=current_user.id,
            role=role,
        )
    except HTTPException:
        return RedirectResponse(
            "/tenant/settings?error=already_member", status_code=303
        )
    await db.commit()

    # Enviar email de invitación si hay backend de email configurado
    if settings.email_configured:
        join_url = f"{settings.APP_BASE_URL}/tenant/join/{invitation.token}"
        tenant = await tenant_service.get_tenant(db, current_user.active_tenant_id)
        tenant_name = tenant.name if tenant else "Trufiq"
        inviter_name = f"{current_user.first_name} {current_user.last_name}".strip()
        html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #5a3e1b;">Te han invitado a {tenant_name} en Trufiq</h2>
  <p>Hola,</p>
  <p><strong>{inviter_name}</strong> te invita a unirte a la organización <strong>{tenant_name}</strong> en Trufiq.</p>
  <p style="margin: 32px 0;">
    <a href="{join_url}"
       style="background: #5a3e1b; color: #fff; padding: 12px 24px;
              text-decoration: none; border-radius: 6px; font-weight: bold;">
      Aceptar invitación
    </a>
  </p>
  <p>O copia esta URL en tu navegador:</p>
  <p style="word-break: break-all; color: #666;">{join_url}</p>
  <p style="color: #999; font-size: 0.85em;">Este enlace caduca en 7 días. Si no esperabas esta invitación, ignora este mensaje.</p>
</body>
</html>
"""
        try:
            await send_email(
                email, f"Invitación para unirte a {tenant_name} en Trufiq", html_body
            )
        except Exception:
            logger.exception("Error enviando email de invitación a %s", email)

    return RedirectResponse("/tenant/settings?invited=1", status_code=303)


@router.post("/invitations/{invitation_id}/revoke", response_class=RedirectResponse)
async def revoke_invitation(
    invitation_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await tenant_service.get_membership(
        db, current_user.active_tenant_id, current_user.id
    )
    if membership is None or membership.role not in ("owner", "admin"):
        return RedirectResponse("/tenant/settings?error=forbidden", status_code=303)

    try:
        await invitation_service.revoke_invitation(
            db,
            invitation_id=invitation_id,
            tenant_id=current_user.active_tenant_id,
        )
    except HTTPException:
        return RedirectResponse("/tenant/settings?error=forbidden", status_code=303)
    await db.commit()
    return RedirectResponse("/tenant/settings?saved=1", status_code=303)


# ── Aceptar invitación ───────────────────────────────────────────────────────


@router.get("/join/{token}", response_class=HTMLResponse)
async def join_tenant_get(
    token: str,
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Muestra la página de confirmación antes de aceptar la invitación."""
    invitation = await invitation_service.get_invitation_for_token(db, token)
    if invitation is None:
        return templates.TemplateResponse(
            request,
            "tenant/join_invalid.html",
            {"request": request, "current_user": current_user},
            status_code=400,
        )

    tenant = await tenant_service.get_tenant(db, invitation.tenant_id)
    return templates.TemplateResponse(
        request,
        "tenant/join.html",
        {
            "request": request,
            "current_user": current_user,
            "invitation": invitation,
            "tenant": tenant,
            "token": token,
        },
    )


@router.post("/join/{token}", response_class=RedirectResponse)
async def join_tenant_post(
    token: str,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Acepta la invitación y añade al usuario al tenant."""
    try:
        await invitation_service.accept_invitation(
            db, token=token, user_id=current_user.id
        )
    except HTTPException:
        return RedirectResponse(f"/tenant/join/{token}", status_code=303)
    await db.commit()
    return RedirectResponse("/?joined=1", status_code=303)
