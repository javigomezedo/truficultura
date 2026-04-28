from __future__ import annotations

import datetime
import re
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.config import settings
from app.database import get_db
from app.i18n import _
from app.jinja import templates
from app.models.user import User
from app.models.lead_capture import LeadCapture
from app.services.admin_service import get_admin_rainfall_overview
from app.services.aemet_service import (
    AemetClient,
    find_aemet_station_for_municipio,
    import_aemet_rainfall,
)
from app.services.ibericam_service import (
    IBERICAM_SLUG_TO_MUNICIPIO,
    fetch_ibericam_sitemap_slugs,
    find_ibericam_slug_for_municipio,
    import_ibericam_rainfall,
)
from app.utils import campaign_year

router = APIRouter(prefix="/admin", tags=["admin"])

# Email validation pattern
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


def is_valid_email(email: str) -> bool:
    """Validate email format"""
    return re.match(EMAIL_PATTERN, email) is not None


_SORT_COLUMNS = {
    "username": User.username,
    "name": User.first_name,
    "email": User.email,
    "role": User.role,
    "status": User.is_active,
    "created_at": User.created_at,
}


@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    sort: str = Query(default="username"),
    order: str = Query(default="asc"),
    status: str = Query(default="all"),
):
    col = _SORT_COLUMNS.get(sort, User.username)
    direction = desc if order == "desc" else asc
    stmt = select(User)
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(User.is_active.is_(False))
    elif status == "unconfirmed":
        stmt = stmt.where(User.email_confirmed.is_(False))
    stmt = stmt.order_by(direction(col))
    result = await db.execute(stmt)
    users = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "admin/users_list.html",
        {
            "request": request,
            "users": users,
            "current_user": current_user,
            "sort": sort,
            "order": order,
            "status": status,
        },
    )


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
    comunidad_regantes: Optional[str] = Form(None),
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

    # Compute role from ADMIN_EMAIL or first-user rule — never accept it from the form
    admin_email_cfg = (settings.ADMIN_EMAIL or "").strip().lower()
    is_admin_email = bool(admin_email_cfg) and email == admin_email_cfg
    if not is_admin_email:
        min_result = await db.execute(select(func.min(User.id)))
        first_user_id = min_result.scalar_one_or_none()
        is_first_user = first_user_id is not None and user.id == first_user_id
    else:
        is_first_user = False
    role = "admin" if (is_admin_email or is_first_user) else "user"

    user.username = username
    user.first_name = first_name.strip()
    user.last_name = last_name.strip()
    user.email = email
    user.role = role
    user.comunidad_regantes = comunidad_regantes == "on"
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


# ---------------------------------------------------------------------------
# Lluvia compartida — panel admin
# ---------------------------------------------------------------------------


@router.get("/lluvia", response_class=HTMLResponse)
async def lluvia_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    overview = await get_admin_rainfall_overview(db)
    return templates.TemplateResponse(
        request,
        "admin/lluvia_overview.html",
        {
            "request": request,
            "current_user": current_user,
            "overview": overview,
            "today": datetime.date.today(),
        },
    )


def _default_date_from(hasta: Optional[datetime.date]) -> datetime.date:
    """Calcula la fecha de inicio sugerida para la importación."""
    if hasta:
        return hasta + datetime.timedelta(days=1)
    today = datetime.date.today()
    cy = campaign_year(today)
    return datetime.date(cy, 5, 1)


@router.get("/lluvia/{municipio_cod}/importar/aemet", response_class=HTMLResponse)
async def lluvia_importar_aemet_form(
    request: Request,
    municipio_cod: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    overview = await get_admin_rainfall_overview(db)
    row = next((o for o in overview if o["municipio_cod"] == municipio_cod), None)
    hasta = row["aemet_hasta"] if row else None
    date_from = _default_date_from(hasta)
    date_to = datetime.date.today()
    municipio_name = row["municipio_name"] if row else municipio_cod

    # Buscar estación AEMET para este municipio descargando el inventario
    suggested_station: Optional[str] = None
    try:
        client = AemetClient()
        all_stations = await client.fetch_dataset(
            "/valores/climatologicos/inventarioestaciones/todasestaciones"
        )
        suggested_station = find_aemet_station_for_municipio(
            all_stations, municipio_cod, municipio_name
        )
    except Exception:
        pass  # Si falla, el campo queda vacío para que el admin lo rellene

    return templates.TemplateResponse(
        request,
        "admin/importar_aemet.html",
        {
            "request": request,
            "current_user": current_user,
            "municipio_cod": municipio_cod,
            "municipio_name": municipio_name,
            "default_date_from": date_from.isoformat(),
            "default_date_to": date_to.isoformat(),
            "aemet_hasta": hasta,
            "suggested_station": suggested_station,
        },
    )


@router.post("/lluvia/{municipio_cod}/importar/aemet")
async def lluvia_importar_aemet_post(
    request: Request,
    municipio_cod: str,
    station_code: str = Form(...),
    municipio_name: Optional[str] = Form(None),
    date_from: datetime.date = Form(...),
    date_to: datetime.date = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        stats = await import_aemet_rainfall(
            db,
            municipio_cod=municipio_cod,
            municipio_name=municipio_name or None,
            station_code=station_code,
            date_from=date_from,
            date_to=date_to,
        )
        await db.commit()
        return JSONResponse({"ok": True, **stats})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.get("/lluvia/{municipio_cod}/importar/ibericam", response_class=HTMLResponse)
async def lluvia_importar_ibericam_form(
    request: Request,
    municipio_cod: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    overview = await get_admin_rainfall_overview(db)
    row = next((o for o in overview if o["municipio_cod"] == municipio_cod), None)
    hasta = row["ibericam_hasta"] if row else None
    date_from = _default_date_from(hasta)
    date_to = datetime.date.today()
    municipio_name = row["municipio_name"] if row else municipio_cod

    # Buscar estaciones ibericam: primero en el diccionario estático, luego
    # en el sitemap dinámico (para cubrir municipios no listados, como mora-de-rubielos).
    known_stations: list[str] = [
        slug for slug, cod in IBERICAM_SLUG_TO_MUNICIPIO.items() if cod == municipio_cod
    ]
    if not known_stations:
        try:
            sitemap_slugs = await fetch_ibericam_sitemap_slugs()
            found = find_ibericam_slug_for_municipio(sitemap_slugs, municipio_name)
            if found:
                known_stations = [found]
        except Exception:
            pass  # Si falla el sitemap, el campo queda vacío
    return templates.TemplateResponse(
        request,
        "admin/importar_ibericam.html",
        {
            "request": request,
            "current_user": current_user,
            "municipio_cod": municipio_cod,
            "municipio_name": municipio_name,
            "default_date_from": date_from.isoformat(),
            "default_date_to": date_to.isoformat(),
            "ibericam_hasta": hasta,
            "known_stations": known_stations,
            "today": date_to,
        },
    )


@router.post("/lluvia/{municipio_cod}/importar/ibericam")
async def lluvia_importar_ibericam_post(
    request: Request,
    municipio_cod: str,
    station_slug: str = Form(...),
    municipio_name: Optional[str] = Form(None),
    date_from: datetime.date = Form(...),
    date_to: datetime.date = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        stats = await import_ibericam_rainfall(
            db,
            station_slug=station_slug,
            municipio_cod=municipio_cod,
            municipio_name=municipio_name or None,
            date_from=date_from,
            date_to=date_to,
        )
        await db.commit()
        return JSONResponse({"ok": True, **stats})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Leads de la landing page
# ---------------------------------------------------------------------------

@router.get("/leads", response_class=HTMLResponse)
async def list_leads(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(LeadCapture).order_by(desc(LeadCapture.created_at)))
    leads = result.scalars().all()
    return templates.TemplateResponse(
        request,
        "admin/leads.html",
        {"request": request, "leads": leads, "current_user": current_user},
    )


@router.post("/leads/{lead_id}/contacted")
async def mark_lead_contacted(
    lead_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(LeadCapture).where(LeadCapture.id == lead_id))
    lead = result.scalars().first()
    if lead and not lead.contacted:
        lead.contacted = True
        lead.contacted_at = datetime.datetime.now(datetime.timezone.utc)
        await db.commit()
    return RedirectResponse(url="/admin/leads", status_code=303)
