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
from app.schemas.rainfall import RainfallCreate, RainfallUpdate
from app.services.rainfall_service import (
    create_rainfall_record,
    delete_rainfall_record,
    get_rainfall_calendar_context,
    get_rainfall_list_context,
    get_rainfall_record,
    update_rainfall_record,
    _get_user_plots,
)

router = APIRouter(prefix="/lluvia", tags=["lluvia"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    year: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    municipio_cod: Optional[str] = Query(default=None),
    only_with_rain: Optional[str] = Query(default=None),
    msg: Optional[str] = None,
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
):
    year_int = int(year) if year else None
    plot_id_int = int(plot_id) if plot_id else None
    source_val = source if source in ("manual", "aemet", "ibericam") else None
    municipio_val = (
        municipio_cod.strip() if municipio_cod and municipio_cod.strip() else None
    )
    context = await get_rainfall_list_context(
        db,
        current_user.active_tenant_id,
        year=year_int,
        plot_id=plot_id_int,
        source=source_val,
        municipio_cod=municipio_val,
        only_with_rain=(only_with_rain == "1"),
        sort_by=sort or "date",
        sort_order=order if order in ("asc", "desc") else "desc",
    )
    return templates.TemplateResponse(
        request,
        "lluvia/list.html",
        {"request": request, **context, "msg": msg},
    )


@router.get("/nuevo", response_class=HTMLResponse)
async def new_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    plots = await _get_user_plots(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "lluvia/form.html",
        {
            "request": request,
            "record": None,
            "plots": plots,
            "action": "/lluvia/",
            "today": datetime.date.today().isoformat(),
        },
    )


@router.post("/", response_class=RedirectResponse)
async def create_view(
    request: Request,
    plot_id: Optional[int] = Form(None),
    municipio_cod: Optional[str] = Form(None),
    date: datetime.date = Form(...),
    precipitation_mm: float = Form(...),
    source: str = Form("manual"),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    try:
        data = RainfallCreate(
            plot_id=plot_id or None,
            municipio_cod=municipio_cod or None,
            date=date,
            precipitation_mm=precipitation_mm,
            source=source,  # type: ignore[arg-type]
            notes=notes or None,
        )
    except Exception:
        plots = await _get_user_plots(db, current_user.active_tenant_id)
        return templates.TemplateResponse(
            request,
            "lluvia/form.html",
            {
                "request": request,
                "record": None,
                "plots": plots,
                "action": "/lluvia/",
                "today": datetime.date.today().isoformat(),
                "error": _("Debes especificar una parcela o un municipio"),
            },
        )

    await create_rainfall_record(db, current_user.active_tenant_id, data)
    return RedirectResponse(
        url=f"/lluvia/?msg={quote_plus(_('Registro de lluvia guardado correctamente'))}",
        status_code=303,
    )


@router.get("/{record_id}/editar", response_class=HTMLResponse)
async def edit_form(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    record = await get_rainfall_record(db, record_id, current_user.active_tenant_id)
    if record is None:
        return RedirectResponse(
            url=f"/lluvia/?msg={quote_plus(_('Registro no encontrado'))}",
            status_code=303,
        )
    if record.created_by_user_id is None:
        return RedirectResponse(
            url=f"/lluvia/?msg={quote_plus(_('Los registros AEMET/Ibericam no se pueden editar'))}",
            status_code=303,
        )
    plots = await _get_user_plots(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "lluvia/form.html",
        {
            "request": request,
            "record": record,
            "plots": plots,
            "action": f"/lluvia/{record_id}/editar",
            "today": datetime.date.today().isoformat(),
        },
    )


@router.post("/{record_id}/editar", response_class=RedirectResponse)
async def edit_view(
    request: Request,
    record_id: int,
    plot_id: Optional[int] = Form(None),
    municipio_cod: Optional[str] = Form(None),
    date: datetime.date = Form(...),
    precipitation_mm: float = Form(...),
    source: str = Form("manual"),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    record = await get_rainfall_record(db, record_id, current_user.active_tenant_id)
    if record is not None and record.created_by_user_id is None:
        return RedirectResponse(
            url=f"/lluvia/?msg={quote_plus(_('Los registros AEMET/Ibericam no se pueden editar'))}",
            status_code=303,
        )
    data = RainfallUpdate(
        plot_id=plot_id or None,
        municipio_cod=municipio_cod or None,
        date=date,
        precipitation_mm=precipitation_mm,
        source=source,  # type: ignore[arg-type]
        notes=notes or None,
    )
    await update_rainfall_record(db, record_id, current_user.active_tenant_id, data)
    return RedirectResponse(
        url=f"/lluvia/?msg={quote_plus(_('Registro de lluvia actualizado correctamente'))}",
        status_code=303,
    )


@router.post("/{record_id}/eliminar", response_class=RedirectResponse)
async def delete_view(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    record = await get_rainfall_record(db, record_id, current_user.active_tenant_id)
    if record is not None and record.created_by_user_id is None:
        return RedirectResponse(
            url=f"/lluvia/?msg={quote_plus(_('Los registros AEMET/Ibericam no se pueden eliminar'))}",
            status_code=303,
        )
    await delete_rainfall_record(db, record_id, current_user.active_tenant_id)
    return RedirectResponse(
        url=f"/lluvia/?msg={quote_plus(_('Registro de lluvia eliminado correctamente'))}",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# Calendario de lluvia
# ---------------------------------------------------------------------------


@router.get("/calendario", response_class=HTMLResponse)
async def calendar_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    year: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    municipio_cod: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
):
    from app.utils import campaign_year

    year_int = int(year) if year else campaign_year(datetime.date.today())
    plot_id_int = int(plot_id) if plot_id else None
    municipio_val = (
        municipio_cod.strip() if municipio_cod and municipio_cod.strip() else None
    )
    source_val = source if source in ("manual", "aemet", "ibericam") else None

    context = await get_rainfall_calendar_context(
        db,
        current_user.active_tenant_id,
        year=year_int,
        plot_id=plot_id_int,
        municipio_cod=municipio_val,
        source=source_val,
    )
    return templates.TemplateResponse(
        request,
        "lluvia/calendario.html",
        {"request": request, **context},
    )
