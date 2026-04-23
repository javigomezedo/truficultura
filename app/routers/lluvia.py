import datetime
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.i18n import _
from app.models.user import User
from app.schemas.rainfall import RainfallCreate, RainfallUpdate
from app.services.ibericam_service import (
    IBERICAM_SLUG_TO_MUNICIPIO,
    import_ibericam_rainfall,
    scrape_ibericam_stations,
)
from app.services.municipios_service import search_municipios
from app.services.aemet_service import import_aemet_rainfall
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
    current_user: User = Depends(require_user),
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
        current_user.id,
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


# ---------------------------------------------------------------------------
# Calendario de lluvia
# ---------------------------------------------------------------------------


@router.get("/calendario", response_class=HTMLResponse)
async def calendar_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    year: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    municipio_cod: Optional[str] = Query(default=None),
):
    from app.utils import campaign_year

    year_int = int(year) if year else campaign_year(datetime.date.today())
    plot_id_int = int(plot_id) if plot_id else None
    municipio_val = (
        municipio_cod.strip() if municipio_cod and municipio_cod.strip() else None
    )

    context = await get_rainfall_calendar_context(
        db,
        current_user.id,
        year=year_int,
        plot_id=plot_id_int,
        municipio_cod=municipio_val,
    )
    return templates.TemplateResponse(
        request,
        "lluvia/calendario.html",
        {"request": request, **context},
    )


# ---------------------------------------------------------------------------
# Importación AEMET
# ---------------------------------------------------------------------------


@router.get("/importar/aemet", response_class=HTMLResponse)
async def importar_aemet_form(
    request: Request,
    current_user: User = Depends(require_user),
):
    today = datetime.date.today()
    return templates.TemplateResponse(
        request,
        "lluvia/importar_aemet.html",
        {
            "request": request,
            "today": today,
            "default_date_from": today.replace(day=1).isoformat(),
            "default_date_to": today.isoformat(),
        },
    )


@router.post("/importar/aemet", response_class=JSONResponse)
async def importar_aemet_post(
    request: Request,
    station_code: Optional[str] = Form(default=""),
    municipio_cod: Optional[str] = Form(default=""),
    municipio_name: Optional[str] = Form(default=""),
    date_from: Optional[str] = Form(default=""),
    date_to: Optional[str] = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    station_code = station_code.strip().upper()
    municipio_cod = municipio_cod.strip()
    municipio_name_val = municipio_name.strip() if municipio_name else None

    if not station_code:
        return JSONResponse(
            {"error": "El código de estación AEMET es obligatorio."}, status_code=400
        )
    if not municipio_cod:
        return JSONResponse(
            {"error": "El código de municipio es obligatorio."}, status_code=400
        )

    try:
        d_from = datetime.date.fromisoformat(date_from)
        d_to = datetime.date.fromisoformat(date_to)
    except ValueError:
        return JSONResponse(
            {"error": "Formato de fecha inválido (usa YYYY-MM-DD)."}, status_code=400
        )

    if d_from > d_to:
        return JSONResponse(
            {"error": "La fecha de inicio no puede ser posterior a la de fin."},
            status_code=400,
        )

    try:
        result = await import_aemet_rainfall(
            db,
            current_user.id,
            municipio_cod=municipio_cod,
            municipio_name=municipio_name_val or None,
            station_code=station_code,
            date_from=d_from,
            date_to=d_to,
        )
        await db.commit()
        return JSONResponse(result)
    except Exception as exc:
        await db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# Importación ibericam
# ---------------------------------------------------------------------------


@router.get("/importar/ibericam", response_class=HTMLResponse)
async def importar_ibericam_form(
    request: Request,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "lluvia/importar_ibericam.html",
        {
            "request": request,
            "slug_map": IBERICAM_SLUG_TO_MUNICIPIO,
            "today": datetime.date.today(),
        },
    )


@router.get("/importar/ibericam/municipios", response_class=JSONResponse)
async def buscar_municipios(
    q: str = Query(default=""),
    current_user: User = Depends(require_user),
) -> JSONResponse:
    """Busca municipios españoles por nombre y devuelve código INE (Nominatim)."""
    municipios = await search_municipios(q)
    return JSONResponse({"municipios": municipios})


@router.get("/importar/ibericam/estaciones", response_class=JSONResponse)
async def estaciones_ibericam(
    current_user: User = Depends(require_user),
) -> JSONResponse:
    """Descubre y devuelve las estaciones ibericam disponibles (JSON).

    Sondea el sitemap y la API de ibericam; puede tardar unos segundos.
    """
    stations = await scrape_ibericam_stations()
    return JSONResponse({"stations": stations})


@router.post("/importar/ibericam", response_class=JSONResponse)
async def importar_ibericam_post(
    request: Request,
    station_slug: str = Form(...),
    municipio_cod: str = Form(...),
    municipio_name: Optional[str] = Form(default=""),
    year: Optional[int] = Form(None),
    month: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    station_slug = station_slug.strip().lower()
    municipio_cod = municipio_cod.strip()
    municipio_name_val = municipio_name.strip() if municipio_name else None

    if not station_slug:
        return JSONResponse(
            {"error": "El slug de la estación es obligatorio."}, status_code=400
        )
    if not municipio_cod:
        return JSONResponse(
            {"error": "El código de municipio es obligatorio."}, status_code=400
        )
    if month is not None and (month < 1 or month > 12):
        return JSONResponse(
            {"error": "El mes debe estar entre 1 y 12."}, status_code=400
        )

    try:
        result = await import_ibericam_rainfall(
            db,
            current_user.id,
            station_slug=station_slug,
            municipio_cod=municipio_cod,
            municipio_name=municipio_name_val or None,
            year=year or None,
            month=month or None,
        )
        await db.commit()
        return JSONResponse(
            {**result, "station_slug": station_slug, "municipio_cod": municipio_cod}
        )
    except Exception as exc:
        await db.rollback()
        return JSONResponse({"error": str(exc)}, status_code=500)
