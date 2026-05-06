from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.jinja import templates
from app.models.notification import NOTIFICATION_TYPES
from app.models.user import User
from app.services.notifications_service import (
    dismiss,
    get_preferences,
    get_unread_count,
    list_notifications,
    mark_all_read,
    mark_read,
    upsert_preference,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

_TYPE_LABELS: dict[str, str] = {
    "campaign_start": "Inicio de campaña agrícola",
    "no_truffle_events": "Sin eventos de trufa",
    "low_water_balance": "Balance hídrico bajo",
    "user_inactive": "Tiempo desconectado",
    "no_rainfall_data": "Sin datos de lluvia",
    "campaign_end_reminder": "Recordatorio fin de campaña",
    "stressed_plant_no_replacement": "Plantas estresadas sin reemplazar",
    "no_irrigation_summer": "Sin riego en verano",
    "no_brule_measurement": "Sin medición de brûlé",
    "low_harvest_vs_previous": "Cosecha baja vs histórico",
}


@router.get("/unread-count")
async def unread_count(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    count = await get_unread_count(current_user.id, db)
    return JSONResponse({"count": count})


@router.get("/", response_class=HTMLResponse)
async def notifications_list(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    show_dismissed: Optional[str] = None,
    msg: Optional[str] = None,
):
    include_dismissed = show_dismissed == "1"
    notifications = await list_notifications(
        current_user.id, db, include_dismissed=include_dismissed
    )
    unread = await get_unread_count(current_user.id, db)
    return templates.TemplateResponse(
        "notifications/index.html",
        {
            "request": request,
            "current_user": current_user,
            "notifications": notifications,
            "unread_count": unread,
            "include_dismissed": include_dismissed,
            "type_labels": _TYPE_LABELS,
            "msg": msg,
        },
    )


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    await mark_read(notification_id, current_user.id, db)
    await db.commit()
    return RedirectResponse("/notifications/", status_code=303)


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    await mark_all_read(current_user.id, db)
    await db.commit()
    return RedirectResponse(
        "/notifications/?msg=Todos+los+avisos+marcados+como+leídos", status_code=303
    )


@router.post("/{notification_id}/dismiss")
async def dismiss_notification(
    notification_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    await dismiss(notification_id, current_user.id, db)
    await db.commit()
    return RedirectResponse("/notifications/", status_code=303)


@router.get("/preferences", response_class=HTMLResponse)
async def preferences_form(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
    msg: Optional[str] = None,
):
    tenant_id = getattr(current_user, "active_tenant_id", None)
    if not tenant_id:
        return RedirectResponse("/", status_code=302)

    prefs = await get_preferences(current_user.id, tenant_id, db)
    return templates.TemplateResponse(
        "notifications/preferences.html",
        {
            "request": request,
            "current_user": current_user,
            "prefs": prefs,
            "notification_types": NOTIFICATION_TYPES,
            "type_labels": _TYPE_LABELS,
            "msg": msg,
        },
    )


@router.post("/preferences")
async def save_preferences(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_id = getattr(current_user, "active_tenant_id", None)
    if not tenant_id:
        return RedirectResponse("/", status_code=302)

    form = await request.form()
    for ntype in NOTIFICATION_TYPES:
        enabled = form.get(f"{ntype}_enabled") == "on"
        email_enabled = form.get(f"{ntype}_email_enabled") == "on"

        raw_days = form.get(f"{ntype}_threshold_days", "")
        threshold_days: Optional[int] = None
        if raw_days and str(raw_days).strip():
            try:
                threshold_days = int(raw_days)
            except ValueError:
                pass

        raw_value = form.get(f"{ntype}_threshold_value", "")
        threshold_value: Optional[float] = None
        if raw_value and str(raw_value).strip():
            try:
                threshold_value = float(str(raw_value).replace(",", "."))
            except ValueError:
                pass

        await upsert_preference(
            user_id=current_user.id,
            tenant_id=tenant_id,
            notification_type=ntype,
            enabled=enabled,
            email_enabled=email_enabled,
            threshold_days=threshold_days,
            threshold_value=threshold_value,
            db=db,
        )
    await db.commit()
    return RedirectResponse(
        "/notifications/preferences?msg=Preferencias+guardadas+correctamente",
        status_code=303,
    )
