import datetime
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.i18n import _
from app.models.user import User
from app.schemas.rainfall import RainfallCreate, RainfallUpdate
from app.services.rainfall_service import (
    create_rainfall_record,
    delete_rainfall_record,
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
    current_user: User = Depends(require_user),
    year: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    msg: Optional[str] = None,
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
):
    year_int = int(year) if year else None
    plot_id_int = int(plot_id) if plot_id else None
    source_val = source if source in ("manual", "aemet", "ibericam") else None
    context = await get_rainfall_list_context(
        db,
        current_user.id,
        year=year_int,
        plot_id=plot_id_int,
        source=source_val,
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
    current_user: User = Depends(require_user),
):
    plots = await _get_user_plots(db, current_user.id)
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
    current_user: User = Depends(require_user),
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
        plots = await _get_user_plots(db, current_user.id)
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

    await create_rainfall_record(db, current_user.id, data)
    return RedirectResponse(
        url=f"/lluvia/?msg={quote_plus(_('Registro de lluvia guardado correctamente'))}",
        status_code=303,
    )


@router.get("/{record_id}/editar", response_class=HTMLResponse)
async def edit_form(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    record = await get_rainfall_record(db, record_id, current_user.id)
    if record is None:
        return RedirectResponse(
            url=f"/lluvia/?msg={quote_plus(_('Registro no encontrado'))}",
            status_code=303,
        )
    plots = await _get_user_plots(db, current_user.id)
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
    current_user: User = Depends(require_user),
):
    data = RainfallUpdate(
        plot_id=plot_id or None,
        municipio_cod=municipio_cod or None,
        date=date,
        precipitation_mm=precipitation_mm,
        source=source,  # type: ignore[arg-type]
        notes=notes or None,
    )
    await update_rainfall_record(db, record_id, current_user.id, data)
    return RedirectResponse(
        url=f"/lluvia/?msg={quote_plus(_('Registro de lluvia actualizado correctamente'))}",
        status_code=303,
    )


@router.post("/{record_id}/eliminar", response_class=RedirectResponse)
async def delete_view(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await delete_rainfall_record(db, record_id, current_user.id)
    return RedirectResponse(
        url=f"/lluvia/?msg={quote_plus(_('Registro de lluvia eliminado correctamente'))}",
        status_code=303,
    )
