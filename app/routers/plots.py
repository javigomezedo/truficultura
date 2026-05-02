import datetime
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
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
from app.services.sigpac_service import SigpacError, fetch_sigpac_data

router = APIRouter(prefix="/plots", tags=["plots"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_plots(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    msg: Optional[str] = None,
):
    plots = await list_plots_service(db, current_user.active_tenant_id)
    plant_counts = await get_plant_counts_by_plot(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "parcelas/list.html",
        {"request": request, "plots": plots, "plant_counts": plant_counts, "msg": msg},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_plot_form(
    request: Request,
    current_user: User = Depends(require_subscription),
):
    return templates.TemplateResponse(
        request,
        "parcelas/form.html",
        {
            "request": request,
            "plot": None,
            "action": "/plots/",
            "method": "post",
            "current_user": current_user,
        },
    )


@router.get("/sigpac-lookup")
async def sigpac_lookup(
    provincia: str = Query(...),
    municipio: str = Query(...),
    poligono: str = Query(...),
    parcela: str = Query(...),
    recinto: str = Query("1"),
    current_user: User = Depends(require_subscription),
):
    # Validate all parameters are numeric to prevent injection
    for param, value in [
        ("provincia", provincia),
        ("municipio", municipio),
        ("poligono", poligono),
        ("parcela", parcela),
        ("recinto", recinto),
    ]:
        if not value.isdigit():
            return JSONResponse(
                status_code=400,
                content={"error": f"El parámetro '{param}' debe ser numérico"},
            )

    try:
        data = await fetch_sigpac_data(provincia, municipio, poligono, parcela, recinto)
    except SigpacError as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={"error": f"Error inesperado consultando SIGPAC: {exc}"},
        )

    return JSONResponse(content=data)


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
    recinto: str = Form("1"),
    caudal_riego: Optional[float] = Form(None),
    provincia_cod: Optional[str] = Form(None),
    municipio_cod: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    await create_plot_service(
        db,
        tenant_id=current_user.active_tenant_id,
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
        recinto=recinto,
        caudal_riego=caudal_riego,
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
    current_user: User = Depends(require_subscription),
):
    obj = await get_plot(db, plot_id, current_user.active_tenant_id)
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
            "current_user": current_user,
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
    recinto: str = Form("1"),
    caudal_riego: Optional[float] = Form(None),
    provincia_cod: Optional[str] = Form(None),
    municipio_cod: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    obj = await get_plot(db, plot_id, current_user.active_tenant_id)
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
        recinto=recinto,
        caudal_riego=caudal_riego,
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
    current_user: User = Depends(require_subscription),
):
    obj = await get_plot(db, plot_id, current_user.active_tenant_id)
    if obj:
        await delete_plot_service(db, obj)
    return RedirectResponse(
        url=f"/plots/?msg={quote_plus(_('Parcela eliminada correctamente'))}",
        status_code=303,
    )
