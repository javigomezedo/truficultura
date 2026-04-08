from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, require_admin
from app.database import get_db
from app.jinja import templates
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])

# Email validation pattern
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


def is_valid_email(email: str) -> bool:
    """Validate email format"""
    return re.match(EMAIL_PATTERN, email) is not None


@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.username))
    users = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "admin/users_list.html",
        {"request": request, "users": users, "current_user": current_user},
    )


@router.get("/users/create", response_class=HTMLResponse)
async def create_user_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return templates.TemplateResponse(
        request,
        "admin/user_create.html",
        {"request": request, "current_user": current_user},
    )


@router.post("/users")
async def create_user(
    request: Request,
    username: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(default="user"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    password = password.strip()
    email = email.strip().lower()

    # Validate email format
    if not is_valid_email(email):
        return templates.TemplateResponse(
            request,
            "admin/user_create.html",
            {
                "request": request,
                "error": "El email no tiene un formato válido.",
                "current_user": current_user,
            },
            status_code=400,
        )

    # Check if username already exists
    result = await db.execute(select(User).where(User.username == username))
    existing = result.scalar_one_or_none()
    if existing:
        return templates.TemplateResponse(
            request,
            "admin/user_create.html",
            {
                "request": request,
                "error": "El usuario ya existe.",
                "current_user": current_user,
            },
            status_code=400,
        )

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return templates.TemplateResponse(
            request,
            "admin/user_create.html",
            {
                "request": request,
                "error": "Este email ya está registrado.",
                "current_user": current_user,
            },
            status_code=400,
        )

    # Validate role
    if role not in ["user", "admin"]:
        role = "user"

    new_user = User(
        username=username,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()

    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
async def edit_user_page(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        return RedirectResponse("/admin/users", status_code=303)

    return templates.TemplateResponse(
        request,
        "admin/user_edit.html",
        {"request": request, "user": user, "current_user": current_user},
    )


@router.post("/users/{user_id}")
async def update_user(
    user_id: int,
    request: Request,
    username: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        return RedirectResponse("/admin/users", status_code=303)

    # Check if username is taken by another user
    if username != user.username:
        result = await db.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()
        if existing:
            return templates.TemplateResponse(
                request,
                "admin/user_edit.html",
                {
                    "request": request,
                    "user": user,
                    "error": "El usuario ya existe.",
                    "current_user": current_user,
                },
                status_code=400,
            )

    # Validate email format
    email = email.strip().lower()
    if not is_valid_email(email):
        return templates.TemplateResponse(
            request,
            "admin/user_edit.html",
            {
                "request": request,
                "user": user,
                "error": "El email no tiene un formato válido.",
                "current_user": current_user,
            },
            status_code=400,
        )

    # Check if email is taken by another user
    if email != user.email:
        result = await db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            return templates.TemplateResponse(
                request,
                "admin/user_edit.html",
                {
                    "request": request,
                    "user": user,
                    "error": "Este email ya está registrado.",
                    "current_user": current_user,
                },
                status_code=400,
            )

    # Validate role
    if role not in ["user", "admin"]:
        role = "user"

    user.username = username
    user.first_name = first_name.strip()
    user.last_name = last_name.strip()
    user.email = email
    user.role = role
    await db.commit()

    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.id:
        return RedirectResponse("/admin/users?error=no-self-delete", status_code=303)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        return RedirectResponse("/admin/users", status_code=303)

    user.is_active = False
    await db.commit()

    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        return RedirectResponse("/admin/users", status_code=303)

    user.is_active = True
    await db.commit()

    return RedirectResponse("/admin/users", status_code=303)
