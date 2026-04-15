import datetime
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.i18n import _
from app.models.user import User
from app.services.plots_service import (
    create_plot as create_plot_service,
    delete_plot as delete_plot_service,
    get_plant_counts_by_plot,
    get_plot,
    list_plots as list_plots_service,
    update_plot as update_plot_service,
)

router = APIRouter(prefix="/plots", tags=["plots"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_plots(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    msg: Optional[str] = None,
):
    plots = await list_plots_service(db, current_user.id)
    plant_counts = await get_plant_counts_by_plot(db, current_user.id)
    return templates.TemplateResponse(
        request,
        "parcelas/list.html",
        {"request": request, "plots": plots, "plant_counts": plant_counts, "msg": msg},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_plot_form(
    request: Request,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "parcelas/form.html",
        {"request": request, "plot": None, "action": "/plots/", "method": "post"},
    )


@router.post("/", response_class=RedirectResponse)
async def create_plot(
    request: Request,
    name: str = Form(...),
    polygon: str = Form(""),
    plot_num: str = Form(""),
    cadastral_ref: str = Form(""),
    hydrant: str = Form(""),
    sector: str = Form(""),
    num_plants: int = Form(0),
    planting_date: datetime.date = Form(...),
    area_ha: Optional[float] = Form(None),
    production_start: Optional[datetime.date] = Form(None),
    has_irrigation: Optional[str] = Form(None),
    provincia_cod: Optional[str] = Form(None),
    municipio_cod: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await create_plot_service(
        db,
        user_id=current_user.id,
        name=name,
        polygon=polygon,
        plot_num=plot_num,
        cadastral_ref=cadastral_ref,
        hydrant=hydrant,
        sector=sector,
        num_plants=num_plants,
        planting_date=planting_date,
        area_ha=area_ha,
        production_start=production_start,
        has_irrigation=has_irrigation == "true",
        provincia_cod=provincia_cod or None,
        municipio_cod=municipio_cod or None,
    )
    return RedirectResponse(
        url=f"/plots/?msg={quote_plus(_('Parcela creada correctamente'))}",
        status_code=303,
    )


@router.get("/{plot_id}/edit", response_class=HTMLResponse)
async def edit_plot_form(
    request: Request,
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    obj = await get_plot(db, plot_id, current_user.id)
    if obj is None:
        return RedirectResponse(
            url=f"/plots/?msg={quote_plus(_('Parcela no encontrada'))}",
            status_code=303,
        )
    return templates.TemplateResponse(
        request,
        "parcelas/form.html",
        {
            "request": request,
            "plot": obj,
            "action": f"/plots/{plot_id}",
            "method": "post",
        },
    )


@router.post("/{plot_id}", response_class=RedirectResponse)
async def update_plot(
    request: Request,
    plot_id: int,
    name: str = Form(...),
    polygon: str = Form(""),
    plot_num: str = Form(""),
    cadastral_ref: str = Form(""),
    hydrant: str = Form(""),
    sector: str = Form(""),
    num_plants: int = Form(0),
    planting_date: datetime.date = Form(...),
    area_ha: Optional[float] = Form(None),
    production_start: Optional[datetime.date] = Form(None),
    has_irrigation: Optional[str] = Form(None),
    provincia_cod: Optional[str] = Form(None),
    municipio_cod: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    obj = await get_plot(db, plot_id, current_user.id)
    if obj is None:
        return RedirectResponse(
            url=f"/plots/?msg={quote_plus(_('Parcela no encontrada'))}",
            status_code=303,
        )

    await update_plot_service(
        db,
        obj,
        name=name,
        polygon=polygon,
        plot_num=plot_num,
        cadastral_ref=cadastral_ref,
        hydrant=hydrant,
        sector=sector,
        num_plants=num_plants,
        planting_date=planting_date,
        area_ha=area_ha,
        production_start=production_start,
        has_irrigation=has_irrigation == "true",
        provincia_cod=provincia_cod or None,
        municipio_cod=municipio_cod or None,
    )
    return RedirectResponse(
        url=f"/plots/?msg={quote_plus(_('Parcela actualizada correctamente'))}",
        status_code=303,
    )


@router.post("/{plot_id}/delete", response_class=RedirectResponse)
async def delete_plot(
    request: Request,
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    obj = await get_plot(db, plot_id, current_user.id)
    if obj:
        await delete_plot_service(db, obj)
    return RedirectResponse(
        url=f"/plots/?msg={quote_plus(_('Parcela eliminada correctamente'))}",
        status_code=303,
    )
