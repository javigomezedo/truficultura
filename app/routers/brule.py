from __future__ import annotations

import datetime
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.i18n import _
from app.models.user import User
from app.plan_access import require_write_access
from app.services import brule_service
from app.services.plants_service import get_plant
from app.services.plots_service import get_plot, list_plots

router = APIRouter(tags=["brule"])
templates = Jinja2Templates(directory="app/templates")


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Global list — all brulé records for tenant
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/brule/", response_class=HTMLResponse)
async def brule_list(
    request: Request,
    plot_id: Optional[str] = Query(default=None),
    campaign: Optional[str] = Query(default=None),
    msg: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    tenant_id = current_user.active_tenant_id
    selected_plot_id = _parse_optional_int(plot_id)
    selected_campaign = _parse_optional_int(campaign)

    records = await brule_service.list_brule_records(
        db,
        tenant_id,
        plot_id=selected_plot_id,
        campaign=selected_campaign,
    )
    plots = await list_plots(db, tenant_id)

    return templates.TemplateResponse(
        request,
        "brule/list.html",
        {
            "request": request,
            "records": records,
            "plots": plots,
            "selected_plot_id": selected_plot_id,
            "selected_campaign": selected_campaign,
            "msg": msg,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Correlation: brulé → production
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/brule/correlacion", response_class=HTMLResponse)
async def brule_correlacion(
    request: Request,
    plot_id: Optional[str] = Query(default=None),
    campaign: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    tenant_id = current_user.active_tenant_id
    selected_plot_id = _parse_optional_int(plot_id)
    selected_campaign = _parse_optional_int(campaign)

    correlation = await brule_service.get_brule_production_correlation(
        db,
        tenant_id,
        plot_id=selected_plot_id,
        campaign=selected_campaign,
    )
    plots = await list_plots(db, tenant_id)

    scatter_data = [
        {
            "x": r["last_diameter_cm"],
            "y": r["total_weight_kg"],
            "label": r["plant_label"],
        }
        for r in correlation
    ]

    return templates.TemplateResponse(
        request,
        "brule/correlacion.html",
        {
            "request": request,
            "correlation": correlation,
            "plots": plots,
            "selected_plot_id": selected_plot_id,
            "selected_campaign": selected_campaign,
            "scatter_data": scatter_data,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-plant evolution — view + create
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/plots/{plot_id}/plants/{plant_id}/brule/", response_class=HTMLResponse)
async def plant_brule_view(
    request: Request,
    plot_id: int,
    plant_id: int,
    msg: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    tenant_id = current_user.active_tenant_id
    plot = await get_plot(db, plot_id, tenant_id)
    if plot is None:
        return RedirectResponse(
            f"/plots/?msg={quote_plus(_('Parcela no encontrada'))}",
            status_code=303,
        )
    plant = await get_plant(db, plant_id, tenant_id)
    if plant is None or plant.plot_id != plot_id:
        return RedirectResponse(
            f"/plots/{plot_id}/map?msg={quote_plus(_('Planta no encontrada'))}",
            status_code=303,
        )

    evolution = await brule_service.get_brule_evolution(db, tenant_id, plant_id)
    records = await brule_service.list_brule_records(db, tenant_id, plant_id=plant_id)

    evo_dates = [str(d) for d, _ in evolution]
    evo_values = [v for _, v in evolution]
    today = datetime.date.today().isoformat()

    return templates.TemplateResponse(
        request,
        "brule/planta.html",
        {
            "request": request,
            "plot": plot,
            "plant": plant,
            "records": records,
            "evo_dates": evo_dates,
            "evo_values": evo_values,
            "today": today,
            "msg": msg,
        },
    )


@router.post("/plots/{plot_id}/plants/{plant_id}/brule/", response_class=HTMLResponse)
async def plant_brule_create(
    request: Request,
    plot_id: int,
    plant_id: int,
    record_date: str = Form(...),
    diameter_cm: int = Form(...),
    next_url: Optional[str] = Query(default=None, alias="next"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_write_access),
):
    tenant_id = current_user.active_tenant_id
    try:
        date = datetime.date.fromisoformat(record_date)
    except ValueError:
        return RedirectResponse(
            f"/plots/{plot_id}/plants/{plant_id}/brule/?msg={quote_plus(_('Fecha inválida'))}",
            status_code=303,
        )

    plot = await get_plot(db, plot_id, tenant_id)
    if plot is None:
        return RedirectResponse(
            f"/plots/?msg={quote_plus(_('Parcela no encontrada'))}",
            status_code=303,
        )

    wants_json = "application/json" in request.headers.get("accept", "")

    try:
        await brule_service.create_brule_record(
            db,
            tenant_id=tenant_id,
            plant_id=plant_id,
            plot_id=plot_id,
            record_date=date,
            diameter_cm=diameter_cm,
            user_id=current_user.id,
        )
    except IntegrityError:
        await db.rollback()
        error_msg = _("Ya existe una medición de brulé para esta planta en esa fecha")
        if wants_json:
            return JSONResponse({"error": error_msg}, status_code=409)
        if next_url and next_url.startswith("/plots/"):
            sep = "&" if "?" in next_url else "?"
            return RedirectResponse(f"{next_url}{sep}msg={quote_plus(error_msg)}", status_code=303)
        return RedirectResponse(
            f"/plots/{plot_id}/plants/{plant_id}/brule/?msg={quote_plus(error_msg)}",
            status_code=303,
        )

    # Success — JSON callers get a redirect URL so they can navigate without a full reload
    if wants_json:
        redirect_to = (
            next_url
            if next_url and next_url.startswith("/plots/")
            else f"/plots/{plot_id}/plants/{plant_id}/brule/"
        )
        return JSONResponse({"ok": True, "redirect": redirect_to}, status_code=200)
    # Allow callers (e.g. the map modal) to redirect back to their page
    if next_url and next_url.startswith("/plots/"):
        return RedirectResponse(next_url, status_code=303)
    return RedirectResponse(
        f"/plots/{plot_id}/plants/{plant_id}/brule/?msg={quote_plus(_('Brulé registrado correctamente'))}",
        status_code=303,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Edit record
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/brule/{record_id}/edit", response_class=HTMLResponse)
async def brule_edit_form(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    tenant_id = current_user.active_tenant_id
    record = await brule_service.get_brule_record(db, record_id, tenant_id)
    if record is None:
        return RedirectResponse(
            f"/brule/?msg={quote_plus(_('Registro no encontrado'))}",
            status_code=303,
        )
    return templates.TemplateResponse(
        request,
        "brule/edit.html",
        {"request": request, "record": record},
    )


@router.post("/brule/{record_id}/edit", response_class=HTMLResponse)
async def brule_edit_submit(
    record_id: int,
    diameter_cm: int = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_write_access),
):
    tenant_id = current_user.active_tenant_id
    record = await brule_service.update_brule_record(
        db, record_id, tenant_id, diameter_cm=diameter_cm
    )
    if record is None:
        return RedirectResponse(
            f"/brule/?msg={quote_plus(_('Registro no encontrado'))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/plots/{record.plot_id}/plants/{record.plant_id}/brule/?msg={quote_plus(_('Brulé actualizado correctamente'))}",
        status_code=303,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Delete record
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/brule/{record_id}/delete", response_class=HTMLResponse)
async def brule_delete(
    record_id: int,
    plant_id_back: Optional[int] = Form(default=None),
    plot_id_back: Optional[int] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_write_access),
):
    tenant_id = current_user.active_tenant_id
    record = await brule_service.get_brule_record(db, record_id, tenant_id)
    if record is not None:
        back_plant = record.plant_id
        back_plot = record.plot_id
        await brule_service.delete_brule_record(db, record_id, tenant_id)
    else:
        back_plant = plant_id_back
        back_plot = plot_id_back

    if back_plant and back_plot:
        return RedirectResponse(
            f"/plots/{back_plot}/plants/{back_plant}/brule/?msg={quote_plus(_('Registro eliminado'))}",
            status_code=303,
        )
    return RedirectResponse(
        f"/brule/?msg={quote_plus(_('Registro eliminado'))}",
        status_code=303,
    )
