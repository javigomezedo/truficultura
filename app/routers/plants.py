from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.models.user import User
from app.services import plants_service, truffle_events_service
from app.services.plots_service import get_plot, list_plots

router = APIRouter(tags=["plants"])
templates = Jinja2Templates(directory="app/templates")

# ─────────────────────────────────────────────────────────────────────────────
# Plant map — view
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/plots/{plot_id}/map", response_class=HTMLResponse)
async def map_view(
    request: Request,
    plot_id: int,
    campaign: Optional[str] = Query(default=None),
    msg: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    plot = await get_plot(db, plot_id, current_user.id)
    if plot is None:
        return RedirectResponse("/plots/?msg=Parcela+no+encontrada", status_code=303)

    selected = int(campaign) if campaign else None
    ctx = await plants_service.get_plot_map_context(
        db, plot, user_id=current_user.id, selected_campaign=selected
    )

    has_events = await plants_service.has_active_truffle_events(
        db, plot_id, current_user.id
    )

    return templates.TemplateResponse(
        request,
        "parcelas/mapa.html",
        {
            "request": request,
            "plot": plot,
            "msg": msg,
            "has_events": has_events,
            **ctx,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plant map — configure
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/plots/{plot_id}/map/configure", response_class=HTMLResponse)
async def configure_map_form(
    request: Request,
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    plot = await get_plot(db, plot_id, current_user.id)
    if plot is None:
        return RedirectResponse("/plots/?msg=Parcela+no+encontrada", status_code=303)

    has_events = await plants_service.has_active_truffle_events(
        db, plot_id, current_user.id
    )

    # Build current row_counts from existing plants
    all_plants = await plants_service.list_plants(db, plot_id, current_user.id)
    row_counts: list[int] = []
    if all_plants:
        current_row = -1
        count = 0
        for p in all_plants:
            if p.row_order != current_row:
                if current_row >= 0:
                    row_counts.append(count)
                current_row = p.row_order
                count = 1
            else:
                count += 1
        row_counts.append(count)

    return templates.TemplateResponse(
        request,
        "parcelas/mapa_configure.html",
        {
            "request": request,
            "plot": plot,
            "has_events": has_events,
            "row_counts": row_counts,
        },
    )


@router.post("/plots/{plot_id}/map/configure", response_class=RedirectResponse)
async def configure_map_submit(
    request: Request,
    plot_id: int,
    row_config: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """row_config is a comma-separated list of integers: '4,5,3'"""
    plot = await get_plot(db, plot_id, current_user.id)
    if plot is None:
        return RedirectResponse("/plots/?msg=Parcela+no+encontrada", status_code=303)

    raw_parts = [p.strip() for p in row_config.split(",") if p.strip()]
    try:
        row_counts = [int(x) for x in raw_parts if int(x) > 0]
    except ValueError:
        return RedirectResponse(
            f"/plots/{plot_id}/map/configure?msg=Formato+incorrecto",
            status_code=303,
        )

    if not row_counts:
        return RedirectResponse(
            f"/plots/{plot_id}/map/configure?msg=Debes+definir+al+menos+una+fila",
            status_code=303,
        )

    try:
        await plants_service.configure_plot_map(
            db, plot, user_id=current_user.id, row_counts=row_counts
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/plots/{plot_id}/map/configure?msg={str(exc).replace(' ', '+')}",
            status_code=303,
        )

    return RedirectResponse(
        f"/plots/{plot_id}/map?msg=Mapa+configurado+correctamente", status_code=303
    )


# ─────────────────────────────────────────────────────────────────────────────
# Truffle event — add (+1) and undo
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/plots/{plot_id}/plants/{plant_id}/add", response_class=RedirectResponse)
async def add_truffle_event(
    request: Request,
    plot_id: int,
    plant_id: int,
    campaign: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    plant = await plants_service.get_plant(db, plant_id, current_user.id)
    if plant is None or plant.plot_id != plot_id:
        return RedirectResponse(
            f"/plots/{plot_id}/map?msg=Planta+no+encontrada", status_code=303
        )

    await truffle_events_service.create_event(
        db,
        plant_id=plant_id,
        plot_id=plot_id,
        user_id=current_user.id,
        source="manual",
    )

    if campaign:
        target = f"/plots/{plot_id}/map?campaign={campaign}&msg=Trufa+registrada+correctamente"
    else:
        target = f"/plots/{plot_id}/map?msg=Trufa+registrada+correctamente"
    return RedirectResponse(target, status_code=303)


@router.post("/plots/{plot_id}/plants/{plant_id}/undo", response_class=RedirectResponse)
async def undo_truffle_event(
    request: Request,
    plot_id: int,
    plant_id: int,
    campaign: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    plant = await plants_service.get_plant(db, plant_id, current_user.id)
    if plant is None or plant.plot_id != plot_id:
        return RedirectResponse(
            f"/plots/{plot_id}/map?msg=Planta+no+encontrada", status_code=303
        )

    undone = await truffle_events_service.undo_last_event(
        db, plant_id=plant_id, user_id=current_user.id
    )

    msg = "Último+registro+deshecho" if undone else "No+hay+registro+para+deshacer"
    if campaign:
        target = f"/plots/{plot_id}/map?campaign={campaign}&msg={msg}"
    else:
        target = f"/plots/{plot_id}/map?msg={msg}"
    return RedirectResponse(target, status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Truffle events list
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/truffles/", response_class=HTMLResponse)
async def list_truffle_events(
    request: Request,
    camp: Optional[str] = Query(default=None),
    plot_id: Optional[int] = Query(default=None),
    plant_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    camp_int = int(camp) if camp else None
    plots = await list_plots(db, current_user.id)

    events = await truffle_events_service.list_events(
        db,
        user_id=current_user.id,
        campaign_year=camp_int,
        plot_id=plot_id,
        plant_id=plant_id,
        include_undone=True,
    )

    if camp_int is not None:
        historical_active_events = await truffle_events_service.list_events(
            db,
            user_id=current_user.id,
            campaign_year=None,
            plot_id=plot_id,
            plant_id=plant_id,
            include_undone=False,
            limit=2000,
        )
    else:
        historical_active_events = [e for e in events if e.undone_at is None]

    summary_rows = truffle_events_service.build_plot_event_summary(
        events, historical_active_events
    )

    return templates.TemplateResponse(
        request,
        "reportes/trufas.html",
        {
            "request": request,
            "events": events,
            "plots": plots,
            "selected_campaign": camp_int,
            "selected_plot_id": plot_id,
            "selected_plant_id": plant_id,
            "summary_rows": summary_rows,
        },
    )
