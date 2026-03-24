from __future__ import annotations

import re
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, verify_password
from app.database import get_db
from app.jinja import templates
from app.models.expense import Expense
from app.models.income import Income
from app.models.plot import Plot
from app.models.user import User

router = APIRouter(tags=["auth"])

# Email validation pattern
EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'


def is_valid_email(email: str) -> bool:
    """Validate email format"""
    return re.match(EMAIL_PATTERN, email) is not None


async def _user_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar_one()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "auth/login.html", {"request": request, "error": None}
    )


@router.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if (
        user is None
        or not user.is_active
        or not verify_password(password, user.hashed_password)
    ):
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Usuario o contraseña incorrectos."},
            status_code=401,
        )

    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    request.session["first_name"] = user.first_name
    request.session["last_name"] = user.last_name
    request.session["email"] = user.email
    return RedirectResponse("/", status_code=303)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "auth/register.html", {"request": request, "error": None}
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
    db: AsyncSession = Depends(get_db),
):
    count = await _user_count(db)

    # Validate email format
    email = email.strip().lower()
    if not is_valid_email(email):
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "error": "El email no tiene un formato válido.",
            },
            status_code=400,
        )

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "error": "Este email ya está registrado.",
            },
            status_code=400,
        )

    password = password.strip()
    password_confirm = password_confirm.strip()

    if password != password_confirm:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "Las contraseñas no coinciden."},
            status_code=400,
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "error": "La contraseña debe tener al menos 8 caracteres.",
            },
            status_code=400,
        )

    if len(password.encode("utf-8")) > 72:
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "error": "La contraseña es demasiado larga (máximo 72 bytes).",
            },
            status_code=400,
        )

    new_user = User(
        username=username,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email,
        hashed_password=hash_password(password),
        role="admin" if count == 0 else "user",
    )
    db.add(new_user)
    await db.flush()

    # Assign all existing unowned records to this first user
    await db.execute(
        update(Plot).where(Plot.user_id.is_(None)).values(user_id=new_user.id)
    )
    await db.execute(
        update(Expense).where(Expense.user_id.is_(None)).values(user_id=new_user.id)
    )
    await db.execute(
        update(Income).where(Income.user_id.is_(None)).values(user_id=new_user.id)
    )

    return RedirectResponse("/login?registered=1", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
