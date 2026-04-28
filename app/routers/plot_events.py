from __future__ import annotations

import calendar as pycalendar
import datetime
from typing import Optional
from urllib.parse import quote_plus, urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.i18n import _
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.user import User
from app.schemas.plot_event import EventType, PlotEventCreate, PlotEventUpdate
from app.services.plot_events_service import (
    create_plot_event,
    delete_plot_event,
    get_plot_event,
    get_plot_events,
    update_plot_event,
)
from app.utils import campaign_year

router = APIRouter(prefix="/plot-events", tags=["plot_events"])
templates = Jinja2Templates(directory="app/templates")

MANUAL_EVENT_TYPES = [
    EventType.LABRADO,
    EventType.PICADO,
    EventType.PODA,
    EventType.VALLADO,
    EventType.INSTALLED_DRIP,
]

MONTH_LABELS = {
    1: _("Enero"),
    2: _("Febrero"),
    3: _("Marzo"),
    4: _("Abril"),
    5: _("Mayo"),
    6: _("Junio"),
    7: _("Julio"),
    8: _("Agosto"),
    9: _("Septiembre"),
    10: _("Octubre"),
    11: _("Noviembre"),
    12: _("Diciembre"),
}

EVENT_LABEL_OVERRIDES = {
    EventType.INSTALLED_DRIP.value: _("Instalación de Riego"),
}

EVENT_COLORS = {
    EventType.LABRADO.value: "#b45309",
    EventType.PICADO.value: "#1d4ed8",
    EventType.PODA.value: "#15803d",
    EventType.VALLADO.value: "#7c3aed",
    EventType.INSTALLED_DRIP.value: "#0e7490",
    EventType.RIEGO.value: "#0891b2",
    EventType.POZO.value: "#475569",
}


def _is_linked_event(record) -> bool:
    return bool(
        getattr(record, "related_irrigation_id", None)
        or getattr(record, "related_well_id", None)
    )


def _parse_event_types(values: Optional[list[str]]) -> Optional[list[EventType]]:
    if not values:
        return None

    parsed: list[EventType] = []
    for value in values:
        try:
            parsed.append(EventType(value))
        except ValueError:
            continue
    return parsed or None


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _event_type_label(event_type: str) -> str:
    return EVENT_LABEL_OVERRIDES.get(
        event_type, event_type.replace("_", " ").capitalize()
    )


def _event_labels_map() -> dict[str, str]:
    return {item.value: _event_type_label(item.value) for item in EventType}


async def _get_all_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    return result.scalars().all()


@router.get("/", response_class=HTMLResponse)
async def root_view():
    return RedirectResponse(url="/plot-events/calendar-view", status_code=303)


@router.get("/list", response_class=HTMLResponse)
async def list_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    plot_id: Optional[str] = Query(default=None),
    campaign: Optional[str] = Query(default=None),
    event_type: Optional[list[str]] = Query(default=None),
    msg: Optional[str] = None,
    msg_type: str = Query(default="success"),
):
    selected_plot = _parse_optional_int(plot_id)
    selected_campaign = _parse_optional_int(campaign)

    event_types = _parse_event_types(event_type)

    # Build campaign selector options from user events (optionally filtered by plot).
    # Only fetch the date column to avoid loading all event data just for the dropdown.
    dates_stmt = select(PlotEvent.date).where(PlotEvent.user_id == current_user.id)
    if selected_plot is not None:
        dates_stmt = dates_stmt.where(PlotEvent.plot_id == selected_plot)
    dates_result = await db.execute(dates_stmt)
    campaign_options = sorted(
        {campaign_year(d) for d in dates_result.scalars().all()}, reverse=True
    )

    effective_date_from = None
    effective_date_to = None

    if selected_campaign is not None:
        campaign_start = datetime.date(selected_campaign, 5, 1)
        campaign_end = datetime.date(selected_campaign + 1, 4, 30)
        effective_date_from = campaign_start
        effective_date_to = campaign_end

    records = []
    if (
        effective_date_from is None
        or effective_date_to is None
        or effective_date_from <= effective_date_to
    ):
        records = await get_plot_events(
            db,
            current_user.id,
            plot_id=selected_plot,
            start_date=effective_date_from,
            end_date=effective_date_to,
            event_types=event_types,
        )

    plots = await _get_all_plots(db, current_user.id)
    event_labels = _event_labels_map()

    return templates.TemplateResponse(
        request,
        "eventos_parcela/list.html",
        {
            "request": request,
            "records": records,
            "plots": plots,
            "event_types": [item.value for item in EventType],
            "event_labels": event_labels,
            "campaign_options": campaign_options,
            "selected_campaign": selected_campaign,
            "selected_plot": selected_plot,
            "selected_event_types": [item.value for item in event_types or []],
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.get("/json/", response_class=JSONResponse)
async def list_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    plot_id: Optional[int] = Query(default=None),
    date_from: Optional[datetime.date] = Query(default=None),
    date_to: Optional[datetime.date] = Query(default=None),
    event_type: Optional[list[str]] = Query(default=None),
):
    event_types = _parse_event_types(event_type)
    records = await get_plot_events(
        db,
        current_user.id,
        plot_id=plot_id,
        start_date=date_from,
        end_date=date_to,
        event_types=event_types,
    )
    return [
        {
            "id": record.id,
            "plot_id": record.plot_id,
            "event_type": record.event_type,
            "date": record.date.isoformat(),
            "notes": record.notes,
            "is_recurring": record.is_recurring,
            "related_irrigation_id": record.related_irrigation_id,
            "related_well_id": record.related_well_id,
        }
        for record in records
    ]


@router.get("/calendar/", response_class=JSONResponse)
async def calendar_json(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    plot_id: Optional[str] = Query(default=None),
    year: Optional[int] = Query(default=None),
    month: Optional[int] = Query(default=None),
    event_type: Optional[list[str]] = Query(default=None),
):
    selected_plot = _parse_optional_int(plot_id)
    event_types = _parse_event_types(event_type)

    records = await get_plot_events(
        db,
        current_user.id,
        plot_id=selected_plot,
        event_types=event_types,
    )

    filtered = []
    for record in records:
        if year is not None and record.date.year != year:
            continue
        if month is not None and record.date.month != month:
            continue
        filtered.append(record)

    grouped: dict[str, list[dict]] = {}
    for record in filtered:
        day_key = record.date.isoformat()
        grouped.setdefault(day_key, []).append(
            {
                "id": record.id,
                "plot_id": record.plot_id,
                "event_type": record.event_type,
                "notes": record.notes,
                "related_irrigation_id": record.related_irrigation_id,
                "related_well_id": record.related_well_id,
            }
        )

    return {"days": grouped, "count": len(filtered)}


@router.get("/calendar-view", response_class=HTMLResponse)
async def calendar_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    plot_id: Optional[str] = Query(default=None),
    year: Optional[int] = Query(default=None),
    month: Optional[int] = Query(default=None),
    event_type: Optional[list[str]] = Query(default=None),
    view: str = Query(default="month"),
    msg: Optional[str] = None,
    msg_type: str = Query(default="success"),
):
    parsed_plot_id: Optional[int] = None
    if plot_id and plot_id.strip():
        try:
            parsed_plot_id = int(plot_id)
        except ValueError:
            parsed_plot_id = None
    plot_id = parsed_plot_id  # type: ignore[assignment]

    today = datetime.date.today()
    selected_year = year or today.year
    selected_month = month or today.month
    selected_month = min(max(selected_month, 1), 12)
    if view not in ("month", "year"):
        view = "month"

    event_types = _parse_event_types(event_type)

    records = await get_plot_events(
        db,
        current_user.id,
        plot_id=plot_id,
        event_types=event_types,
    )
    event_labels = _event_labels_map()
    plots = await _get_all_plots(db, current_user.id)

    selected_event_types = [item.value for item in event_types or []]
    base_nav_params = {
        "plot_id": plot_id or "",
        "year": selected_year,
        "month": selected_month,
        "view": view,
    }
    if selected_event_types:
        base_nav_params["event_type"] = selected_event_types
    nav_query = urlencode(base_nav_params, doseq=True)

    cal = pycalendar.Calendar(firstweekday=0)

    # ── month view data ────────────────────────────────────────────────
    filtered_month = [
        r
        for r in records
        if r.date.year == selected_year and r.date.month == selected_month
    ]
    events_by_day: dict[int, list] = {}
    for r in filtered_month:
        events_by_day.setdefault(r.date.day, []).append(r)

    month_grid = cal.monthdayscalendar(selected_year, selected_month)

    prev_month = selected_month - 1
    prev_year = selected_year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    next_month = selected_month + 1
    next_year = selected_year
    if next_month == 13:
        next_month = 1
        next_year += 1

    # ── year view data ─────────────────────────────────────────────────
    filtered_year = [r for r in records if r.date.year == selected_year]
    # events_by_month_day[month][day] = [events]
    events_by_month_day: dict[int, dict[int, list]] = {m: {} for m in range(1, 13)}
    for r in filtered_year:
        events_by_month_day[r.date.month].setdefault(r.date.day, []).append(r)

    year_grids = {m: cal.monthdayscalendar(selected_year, m) for m in range(1, 13)}

    years_in_records = sorted({r.date.year for r in records})
    if years_in_records:
        year_start = min(years_in_records)
        year_end = max(years_in_records)
        year_options = list(range(year_start, year_end + 1))
    else:
        year_options = list(range(selected_year - 10, selected_year + 2))
    if selected_year not in year_options:
        year_options.append(selected_year)
        year_options.sort()

    today = datetime.date.today()

    return templates.TemplateResponse(
        request,
        "eventos_parcela/calendar.html",
        {
            "request": request,
            "plots": plots,
            "selected_plot": plot_id,
            "selected_year": selected_year,
            "selected_month": selected_month,
            "month_name": MONTH_LABELS.get(
                selected_month, pycalendar.month_name[selected_month]
            ),
            "month_grid": month_grid,
            "events_by_day": events_by_day,
            "prev_month": prev_month,
            "prev_year": prev_year,
            "next_month": next_month,
            "next_year": next_year,
            "view": view,
            "year_grids": year_grids,
            "events_by_month_day": events_by_month_day,
            "month_names": MONTH_LABELS,
            "month_options": list(range(1, 13)),
            "year_options": year_options,
            "event_labels": event_labels,
            "event_colors": EVENT_COLORS,
            "event_types": [item.value for item in EventType],
            "selected_event_types": selected_event_types,
            "today_year": today.year,
            "today_month": today.month,
            "today_day": today.day,
            "nav_query": nav_query,
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    date: Optional[datetime.date] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    event_type: Optional[list[str]] = Query(default=None),
    view_mode: str = Query(default="list"),
):
    selected_plot = _parse_optional_int(plot_id)
    event_types = _parse_event_types(event_type)
    selected_event_types = [item.value for item in event_types or []]

    focus_date = date or datetime.date.today()

    # Determine view mode for back button
    if view_mode not in ("month", "year", "list"):
        view_mode = "list"

    if view_mode == "year":
        back_view = "year"
    else:
        back_view = "month"

    back_params = {
        "plot_id": selected_plot or "",
        "year": focus_date.year,
        "month": focus_date.month,
        "view": back_view,
    }
    if selected_event_types:
        back_params["event_type"] = selected_event_types
    back_to_calendar_url = (
        f"/plot-events/calendar-view?{urlencode(back_params, doseq=True)}"
    )

    plots = await _get_all_plots(db, current_user.id)
    event_labels = _event_labels_map()
    return templates.TemplateResponse(
        request,
        "eventos_parcela/form.html",
        {
            "request": request,
            "record": None,
            "plots": plots,
            "selected_plot": selected_plot,
            "selected_date": date,
            "selected_event_types": selected_event_types,
            "back_to_calendar_url": back_to_calendar_url,
            "view_mode": view_mode,
            "event_types": MANUAL_EVENT_TYPES,
            "event_labels": event_labels,
            "action": "/plot-events/",
        },
    )


@router.post("/", response_class=RedirectResponse)
async def create_view(
    request: Request,
    plot_id: int = Form(...),
    event_type: str = Form(...),
    date: datetime.date = Form(...),
    notes: Optional[str] = Form(None),
    view_mode: str = Form(default="list"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = PlotEventCreate(
        plot_id=plot_id,
        event_type=EventType(event_type),
        date=date,
        notes=notes or None,
    )
    try:
        await create_plot_event(db, current_user.id, data)
    except HTTPException as e:
        # Capture validation errors and redirect with error message
        if view_mode == "month":
            redirect_url = f"/plot-events/calendar-view?year={date.year}&month={date.month}&msg={quote_plus(e.detail)}&msg_type=error"
        elif view_mode == "year":
            redirect_url = f"/plot-events/calendar-view?year={date.year}&view=year&msg={quote_plus(e.detail)}&msg_type=error"
        else:  # list
            redirect_url = (
                f"/plot-events/list?msg={quote_plus(e.detail)}&msg_type=error"
            )
        return RedirectResponse(url=redirect_url, status_code=303)

    # Determine redirect URL based on view_mode
    if view_mode == "month":
        redirect_url = f"/plot-events/calendar-view?year={date.year}&month={date.month}&msg={quote_plus(_('Evento registrado correctamente'))}&msg_type=success"
    elif view_mode == "year":
        redirect_url = f"/plot-events/calendar-view?year={date.year}&view=year&msg={quote_plus(_('Evento registrado correctamente'))}&msg_type=success"
    else:  # list
        redirect_url = f"/plot-events/list?msg={quote_plus(_('Evento registrado correctamente'))}&msg_type=success"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/{event_id}/edit", response_class=HTMLResponse)
async def edit_form(
    request: Request,
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    record = await get_plot_event(db, event_id, current_user.id)
    if record is None:
        return RedirectResponse(
            url=f"/plot-events/list?msg={quote_plus(_('Evento no encontrado'))}",
            status_code=303,
        )
    if _is_linked_event(record):
        return RedirectResponse(
            url=f"/plot-events/list?msg={quote_plus(_('Este evento está enlazado y no se puede editar desde aquí'))}",
            status_code=303,
        )

    plots = await _get_all_plots(db, current_user.id)
    event_labels = _event_labels_map()
    return templates.TemplateResponse(
        request,
        "eventos_parcela/form.html",
        {
            "request": request,
            "record": record,
            "plots": plots,
            "event_types": MANUAL_EVENT_TYPES,
            "event_labels": event_labels,
            "action": f"/plot-events/{event_id}/edit",
        },
    )


@router.post("/{event_id}/edit", response_class=RedirectResponse)
async def update_view(
    request: Request,
    event_id: int,
    event_type: str = Form(...),
    date: datetime.date = Form(...),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    record = await get_plot_event(db, event_id, current_user.id)
    if record is None:
        return RedirectResponse(
            url=f"/plot-events/list?msg={quote_plus(_('Evento no encontrado'))}&msg_type=error",
            status_code=303,
        )
    if _is_linked_event(record):
        return RedirectResponse(
            url=f"/plot-events/list?msg={quote_plus(_('Este evento está enlazado y no se puede editar desde aquí'))}&msg_type=error",
            status_code=303,
        )

    data = PlotEventUpdate(
        event_type=EventType(event_type),
        date=date,
        notes=notes or None,
    )
    try:
        await update_plot_event(db, record, data)
    except HTTPException as e:
        # Capture validation errors and redirect with error message
        return RedirectResponse(
            url=f"/plot-events/list?msg={quote_plus(e.detail)}&msg_type=error",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/plot-events/list?msg={quote_plus(_('Evento actualizado correctamente'))}&msg_type=success",
        status_code=303,
    )


@router.post("/{event_id}/delete", response_class=RedirectResponse)
async def delete_view(
    request: Request,
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    record = await get_plot_event(db, event_id, current_user.id)
    if record is not None and _is_linked_event(record):
        return RedirectResponse(
            url=f"/plot-events/list?msg={quote_plus(_('Este evento está enlazado y no se puede eliminar desde aquí'))}&msg_type=error",
            status_code=303,
        )

    await delete_plot_event(db, event_id, current_user.id)
    return RedirectResponse(
        url=f"/plot-events/list?msg={quote_plus(_('Evento eliminado correctamente'))}&msg_type=success",
        status_code=303,
    )
