from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.jinja import templates
from app.models.expense import Expense
from app.models.income import Income
from app.models.plot import Plot
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User
from app.services.email_service import (
    send_confirmation_email,
    send_password_reset_email,
)
from app.services import billing_service
from app.services.token_service import (
    EMAIL_CONFIRMATION_SALT,
    PASSWORD_RESET_SALT,
    confirm_token,
    generate_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Email validation pattern
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


def is_valid_email(email: str) -> bool:
    """Validate email format"""
    return re.match(EMAIL_PATTERN, email) is not None


async def _user_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar_one()


def _safe_next(next_url: Optional[str]) -> str:
    """Return next_url only when it is a safe relative path."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: Optional[str] = Query(default=None),
):
    if request.session.get("user_id"):
        return RedirectResponse(_safe_next(next), status_code=303)

    next_url = next
    pending_scan = request.session.get("pending_scan")
    if not next_url and pending_scan:
        next_url = f"/scan/{pending_scan}"

    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {"request": request, "error": None, "next_url": next_url or ""},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_url: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    # Check if user exists and password is correct
    if user is not None and verify_password(password, user.hashed_password):
        # Check email confirmed first (separate from admin-deactivated)
        if not user.email_confirmed:
            return templates.TemplateResponse(
                request,
                "auth/login.html",
                {
                    "request": request,
                    "error": "Debes confirmar tu dirección de email antes de acceder. Revisa tu bandeja de entrada.",
                    "next_url": next_url or "",
                },
                status_code=401,
            )
        # User exists and password is correct, but check if active
        if not user.is_active:
            return templates.TemplateResponse(
                request,
                "auth/login.html",
                {
                    "request": request,
                    "error": "Este usuario ha sido desactivado. Por favor, contacta con el administrador si necesitas reactivar tu cuenta.",
                    "next_url": next_url or "",
                },
                status_code=401,
            )
        # User is active and confirmed, proceed with login
        request.session["user_id"] = user.id
        request.session["username"] = user.username
        request.session["role"] = user.role
        request.session["first_name"] = user.first_name
        request.session["last_name"] = user.last_name
        request.session["email"] = user.email

        # Load tenant to check subscription status
        membership_result = await db.execute(
            select(TenantMembership).where(TenantMembership.user_id == user.id)
        )
        membership = membership_result.scalar_one_or_none()
        if membership:
            tenant_result = await db.execute(
                select(Tenant).where(Tenant.id == membership.tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
            user.active_tenant = tenant  # type: ignore[attr-defined]
        else:
            user.active_tenant = None  # type: ignore[attr-defined]

        # If trial expired or subscription lapsed, send directly to billing
        from app.auth import is_subscription_blocked
        if is_subscription_blocked(user):
            return RedirectResponse("/billing/subscribe", status_code=303)

        if not next_url:
            pending_scan = request.session.get("pending_scan")
            if pending_scan:
                next_url = f"/scan/{pending_scan}"

        redirect_to = _safe_next(next_url) if next_url else "/"
        if redirect_to.startswith("/scan/"):
            request.session.pop("pending_scan", None)
        return RedirectResponse(redirect_to, status_code=303)

    # Either user doesn't exist or password is wrong
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {"request": request, "error": "Usuario o contraseña incorrectos.", "next_url": next_url or ""},
        status_code=401,
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    next: Optional[str] = Query(default=None),
):
    if request.session.get("user_id"):
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(
        request,
        "auth/register.html",
        {"request": request, "error": None, "next_url": next or ""},
    )


@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    username: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    comunidad_regantes: Optional[str] = Form(None),
    next_url: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    count = await _user_count(db)

    # Validate email format
    email = email.strip().lower()
    _reg_error_ctx = {"request": request, "next_url": next_url or ""}

    if not is_valid_email(email):
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {**_reg_error_ctx, "error": "El email no tiene un formato válido."},
            status_code=400,
        )

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {**_reg_error_ctx, "error": "Este email ya está registrado."},
            status_code=400,
        )

    password = password.strip()
    password_confirm = password_confirm.strip()

    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {**_reg_error_ctx, "error": "Las contraseñas no coinciden."},
            status_code=400,
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {**_reg_error_ctx, "error": "La contraseña debe tener al menos 8 caracteres."},
            status_code=400,
        )

    if len(password.encode("utf-8")) > 72:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {**_reg_error_ctx, "error": "La contraseña es demasiado larga (máximo 72 bytes)."},
            status_code=400,
        )

    # Determine role and confirmation status
    admin_email = (settings.ADMIN_EMAIL or "").strip().lower()
    is_admin_email = bool(admin_email) and email == admin_email
    is_first_user = count == 0 and not admin_email

    if is_admin_email or is_first_user:
        # Admin user: immediately active and confirmed
        role = "admin"
        is_active = True
        email_confirmed = True
    else:
        role = "user"
        is_active = False
        email_confirmed = False

    # In dev mode (no email backend) activate directly so the app is usable without a mail server
    if not email_confirmed and not settings.email_configured:
        is_active = True
        email_confirmed = True

    new_user = User(
        username=username,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email,
        hashed_password=hash_password(password),
        role=role,
        is_active=is_active,
        email_confirmed=email_confirmed,
        comunidad_regantes=(comunidad_regantes == "on"),
    )
    db.add(new_user)
    await db.flush()

    # Create a tenant for this user (1-person tenant for independent farmers)
    full_name = f"{new_user.first_name} {new_user.last_name}".strip() or new_user.username
    base_slug = re.sub(r"[^\w\s-]", "", full_name.lower()).strip()
    base_slug = re.sub(r"[\s_]+", "-", base_slug) or f"user-{new_user.id}"

    # Ensure slug uniqueness
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
        user_id=new_user.id,
        role="owner",
    )
    db.add(membership)
    await db.flush()

    # Assign all existing unowned records to the first registered user's tenant
    if is_admin_email or is_first_user:
        await db.execute(
            update(Plot).where(Plot.tenant_id.is_(None)).values(tenant_id=new_tenant.id)
        )
        await db.execute(
            update(Expense).where(Expense.tenant_id.is_(None)).values(tenant_id=new_tenant.id)
        )
        await db.execute(
            update(Income).where(Income.tenant_id.is_(None)).values(tenant_id=new_tenant.id)
        )

    await db.commit()

    # Start trial for immediately confirmed users (admins, first user, or dev mode)
    if new_user.email_confirmed:
        await billing_service.start_trial(new_tenant, db)

    if not new_user.email_confirmed:
        # Send confirmation email (SMTP is configured at this point)
        token = generate_token(email, EMAIL_CONFIRMATION_SALT)
        safe_next = _safe_next(next_url) if next_url else ""
        await send_confirmation_email(
            email, token, next_url=safe_next if safe_next and safe_next != "/" else None
        )
        pending_url = (
            f"/login?pending_confirmation=1&next={safe_next}"
            if safe_next and safe_next != "/"
            else "/login?pending_confirmation=1"
        )
        return RedirectResponse(pending_url, status_code=303)

    safe_next = _safe_next(next_url) if next_url else ""
    redirect_target = f"/login?registered=1&next={safe_next}" if safe_next and safe_next != "/" else "/login?registered=1"
    return RedirectResponse(redirect_target, status_code=303)


@router.get("/register/confirm/{token}", response_class=HTMLResponse)
async def register_confirm(
    token: str,
    next: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    email = confirm_token(token, EMAIL_CONFIRMATION_SALT, max_age=86400)  # 24 h
    if not email:
        return RedirectResponse("/login?confirm_error=1", status_code=303)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse("/login?confirm_error=1", status_code=303)

    if user.email_confirmed:
        return RedirectResponse("/login?already_confirmed=1", status_code=303)

    user.email_confirmed = True
    user.is_active = True
    await db.commit()

    # Load the tenant for this user to start the trial
    membership_result = await db.execute(
        select(TenantMembership).where(TenantMembership.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()
    if membership:
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.id == membership.tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant:
            await billing_service.start_trial(tenant, db)

    safe_next = _safe_next(next) if next else ""
    redirect_target = (
        f"/login?confirmed=1&next={safe_next}"
        if safe_next and safe_next != "/"
        else "/login?confirmed=1"
    )
    return RedirectResponse(redirect_target, status_code=303)


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "auth/forgot_password.html", {"request": request, "sent": False}
    )


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_post(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Always redirect to the same destination to avoid email enumeration
    if user and user.email_confirmed and user.is_active:
        token = generate_token(email, PASSWORD_RESET_SALT)
        if settings.email_configured:
            await send_password_reset_email(email, token)
        else:
            reset_url = f"{settings.APP_BASE_URL}/reset-password/{token}"
            logger.info("[dev] Password reset link for %s: %s", email, reset_url)

    return RedirectResponse("/login?reset_sent=1", status_code=303)


@router.get("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_page(token: str, request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    # Validate token early so we can show an error page immediately
    email = confirm_token(token, PASSWORD_RESET_SALT, max_age=3600)  # 1 h
    if not email:
        return RedirectResponse("/login?reset_error=1", status_code=303)
    return templates.TemplateResponse(
        request,
        "auth/reset_password.html",
        {"request": request, "token": token, "error": None},
    )


@router.post("/reset-password/{token}", response_class=HTMLResponse)
async def reset_password_post(
    token: str,
    request: Request,
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    email = confirm_token(token, PASSWORD_RESET_SALT, max_age=3600)  # 1 h
    if not email:
        return RedirectResponse("/login?reset_error=1", status_code=303)

    password = password.strip()
    password_confirm = password_confirm.strip()

    def _render_reset_error(msg: str):
        return templates.TemplateResponse(
            request,
            "auth/reset_password.html",
            {"request": request, "token": token, "error": msg},
            status_code=400,
        )

    if password != password_confirm:
        return _render_reset_error("Las contraseñas no coinciden.")
    if len(password) < 8:
        return _render_reset_error("La contraseña debe tener al menos 8 caracteres.")
    if len(password.encode("utf-8")) > 72:
        return _render_reset_error(
            "La contraseña es demasiado larga (máximo 72 bytes)."
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse("/login?reset_error=1", status_code=303)

    user.hashed_password = hash_password(password)
    await db.commit()
    return RedirectResponse("/login?password_reset=1", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
