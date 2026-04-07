from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, require_admin
from app.database import get_db
from app.jinja import templates
from app.models.plot import Plot
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


@router.get("/qr", response_class=HTMLResponse)
async def qr_management_page(
    request: Request,
    selected_user_id: Optional[int] = Query(default=None, alias="user_id"),
    selected_plot_id: Optional[int] = Query(default=None, alias="plot_id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users_result = await db.execute(select(User).order_by(User.username))
    users = users_result.scalars().all()

    plots: list[Plot] = []
    if selected_user_id is not None:
        plots_result = await db.execute(
            select(Plot).where(Plot.user_id == selected_user_id).order_by(Plot.name)
        )
        plots = plots_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/qr_management.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
            "plots": plots,
            "selected_user_id": selected_user_id,
            "selected_plot_id": selected_plot_id,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# QR PDF generation
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/users/{user_id}/plots/{plot_id}/qr-pdf")
async def download_qr_pdf(
    request: Request,
    user_id: int,
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Generate a PDF with one QR code per plant for field harvesting."""
    import io

    import qrcode
    from fpdf import FPDF

    from app.routers.scan import sign_plant_token
    from app.services.plants_service import list_plants
    from app.services.plots_service import get_plot

    plot = await get_plot(db, plot_id, user_id)
    if plot is None:
        return RedirectResponse("/admin/users", status_code=303)

    plants = await list_plants(db, plot_id, user_id)
    if not plants:
        return RedirectResponse(
            "/admin/users?msg=La+parcela+no+tiene+plantas+configuradas",
            status_code=303,
        )

    base_url = str(request.base_url).rstrip("/")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)

    cell_w, cell_h = 50.0, 60.0
    margin_x, margin_y = 10.0, 10.0
    cols = 4
    qr_size = 35.0

    col = 0
    row_y = margin_y

    for plant in plants:
        if col == 0:
            pdf.add_page()
            row_y = margin_y

        x = margin_x + col * cell_w
        scan_url = f"{base_url}/scan/{sign_plant_token(plant.id)}"

        # Generate QR image into a bytes buffer
        img = qrcode.make(scan_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        qr_x = x + (cell_w - qr_size) / 2
        pdf.image(buf, x=qr_x, y=row_y, w=qr_size, h=qr_size)

        # Plant label below the QR
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_xy(x, row_y + qr_size + 2)
        pdf.cell(cell_w, 6, plant.label, align="C")

        # Plot name below label
        pdf.set_font("Helvetica", "", 8)
        pdf.set_xy(x, row_y + qr_size + 9)
        pdf.cell(cell_w, 5, plot.name, align="C")

        col += 1
        if col >= cols:
            col = 0
            row_y += cell_h

    pdf_bytes = pdf.output()
    filename = f"qr_{plot.name.replace(' ', '_')}_{user_id}.pdf"

    from fastapi.responses import Response

    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
