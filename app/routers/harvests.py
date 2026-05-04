from __future__ import annotations

import datetime
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.i18n import _
from app.models.user import User
from app.services import plot_harvest_service, truffle_events_service
from app.services.plots_service import list_plots
from app.utils import campaign_year as _campaign_year

router = APIRouter(tags=["harvests"])
templates = Jinja2Templates(directory="app/templates")


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_eu_float(value: str) -> float:
    """Parse European-format number string (comma as decimal, dot as thousands)."""
    cleaned = value.strip().replace(".", "").replace(",", ".")
    return float(cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# Production total (combined Por planta + Por bancal)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/production/", response_class=HTMLResponse)
async def production_total(
    request: Request,
    camp: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    camp_int = _parse_optional_int(camp)
    plot_id_int = _parse_optional_int(plot_id)

    plots = await list_plots(db, current_user.active_tenant_id)
    plot_name_map = {p.id: p.name for p in plots}

    # Fetch TruffleEvents (plant-level) filtered by scope
    events = await truffle_events_service.list_events(
        db,
        tenant_id=current_user.active_tenant_id,
        campaign_year=camp_int,
        plot_id=plot_id_int,
        include_undone=False,
        limit=5000,
    )

    # Fetch PlotHarvests (bancal-level) filtered by scope
    harvests = await plot_harvest_service.list_harvests(
        db,
        tenant_id=current_user.active_tenant_id,
        campaign_year_filter=camp_int,
        plot_id=plot_id_int,
    )

    # Compute union of campaign years from both sources
    event_campaign_years = {
        _campaign_year(e.created_at.date())
        for e in events
        if getattr(e, "created_at", None) is not None
    }
    harvest_campaign_years = await plot_harvest_service.get_campaign_years(
        db, tenant_id=current_user.active_tenant_id
    )
    # We need all campaign years, not just those in the filtered result, so
    # also fetch event years without filters for the selector
    year_events = await truffle_events_service.list_events(
        db,
        tenant_id=current_user.active_tenant_id,
        campaign_year=None,
        plot_id=None,
        include_undone=False,
        limit=5000,
    )
    all_event_years = {
        _campaign_year(e.created_at.date())
        for e in year_events
        if getattr(e, "created_at", None) is not None
    }
    campaign_years = sorted(all_event_years | set(harvest_campaign_years), reverse=True)

    # Per-plot summary
    plant_grams_by_plot: dict[int, float] = {}
    for e in events:
        w = float(getattr(e, "estimated_weight_grams", 0) or 0)
        plant_grams_by_plot[e.plot_id] = plant_grams_by_plot.get(e.plot_id, 0.0) + w

    harvest_grams_by_plot: dict[int, float] = {}
    for h in harvests:
        harvest_grams_by_plot[h.plot_id] = (
            harvest_grams_by_plot.get(h.plot_id, 0.0) + h.weight_grams
        )

    all_plot_ids = sorted(set(plant_grams_by_plot) | set(harvest_grams_by_plot))
    summary_rows = [
        {
            "plot_id": pid,
            "plot_name": plot_name_map.get(pid, f"Parcela {pid}"),
            "plant_grams": round(plant_grams_by_plot.get(pid, 0.0), 2),
            "harvest_grams": round(harvest_grams_by_plot.get(pid, 0.0), 2),
            "total_grams": round(
                plant_grams_by_plot.get(pid, 0.0) + harvest_grams_by_plot.get(pid, 0.0),
                2,
            ),
        }
        for pid in all_plot_ids
    ]

    # Combined chronological list
    combined: list[dict] = []
    for e in events:
        combined.append(
            {
                "date": e.created_at.date() if getattr(e, "created_at", None) else None,
                "plot_name": plot_name_map.get(e.plot_id, f"Parcela {e.plot_id}"),
                "type": "planta",
                "detail": (
                    e.plant.label
                    if getattr(e, "plant", None) and getattr(e.plant, "label", None)
                    else str(e.plant_id)
                ),
                "weight_grams": float(getattr(e, "estimated_weight_grams", 0) or 0),
            }
        )
    for h in harvests:
        combined.append(
            {
                "date": h.harvest_date,
                "plot_name": plot_name_map.get(h.plot_id, f"Parcela {h.plot_id}"),
                "type": "bancal",
                "detail": h.notes or "",
                "weight_grams": h.weight_grams,
            }
        )
    combined.sort(key=lambda r: r["date"] or datetime.date.min, reverse=True)

    return templates.TemplateResponse(
        request,
        "produccion/total.html",
        {
            "request": request,
            "plots": plots,
            "selected_campaign": camp_int,
            "selected_plot_id": plot_id_int,
            "campaign_years": campaign_years,
            "summary_rows": summary_rows,
            "combined": combined,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Harvest list
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/harvests/", response_class=HTMLResponse)
async def list_harvests(
    request: Request,
    camp: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    camp_int = _parse_optional_int(camp)
    plot_id_int = _parse_optional_int(plot_id)

    plots = await list_plots(db, current_user.active_tenant_id)
    campaign_years_harvests = await plot_harvest_service.get_campaign_years(
        db, tenant_id=current_user.active_tenant_id
    )

    harvests = await plot_harvest_service.list_harvests(
        db,
        tenant_id=current_user.active_tenant_id,
        campaign_year_filter=camp_int,
        plot_id=plot_id_int,
    )

    # Summary by plot for the selected scope
    totals_by_plot = await plot_harvest_service.get_totals_by_plot(
        db,
        tenant_id=current_user.active_tenant_id,
        campaign_year_filter=camp_int,
    )
    # Build ordered summary rows aligned with plots
    summary_rows = [
        {
            "plot_id": p.id,
            "plot_name": p.name,
            "total_grams": totals_by_plot.get(p.id, 0.0),
        }
        for p in plots
        if p.id in totals_by_plot
    ]

    return templates.TemplateResponse(
        request,
        "produccion/por_bancal.html",
        {
            "request": request,
            "harvests": harvests,
            "plots": plots,
            "selected_campaign": camp_int,
            "selected_plot_id": plot_id_int,
            "campaign_years": campaign_years_harvests,
            "summary_rows": summary_rows,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# New harvest — GET form
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/harvests/new", response_class=HTMLResponse)
async def new_harvest_form(
    request: Request,
    plot_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    plots = await list_plots(db, current_user.active_tenant_id)
    today = datetime.date.today().isoformat()
    return templates.TemplateResponse(
        request,
        "produccion/form_bancal.html",
        {
            "request": request,
            "plots": plots,
            "harvest": None,
            "selected_plot_id": _parse_optional_int(plot_id),
            "today": today,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# New harvest — POST submit (per-plot rows)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/harvests/new", response_class=RedirectResponse)
async def create_harvest_batch(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    form = await request.form()
    harvest_date_str = form.get("harvest_date", "")
    try:
        harvest_date = datetime.date.fromisoformat(str(harvest_date_str))
    except (ValueError, TypeError):
        plots = await list_plots(db, current_user.active_tenant_id)
        return templates.TemplateResponse(
            request,
            "produccion/form_bancal.html",
            {
                "request": request,
                "plots": plots,
                "harvest": None,
                "selected_plot_id": None,
                "today": datetime.date.today().isoformat(),
                "error": _("Fecha inválida"),
            },
            status_code=422,
        )

    entries = []
    for plot_id_str, grams_str in form.multi_items():
        if not plot_id_str.startswith("grams_"):
            continue
        plot_id = int(plot_id_str.removeprefix("grams_"))
        grams_raw = str(grams_str).strip()
        if (
            not grams_raw
            or grams_raw == "0"
            or grams_raw == "0,0"
            or grams_raw == "0.0"
        ):
            continue
        try:
            grams = _parse_eu_float(grams_raw)
        except (ValueError, AttributeError):
            continue
        notes_key = f"notes_{plot_id}"
        notes = str(form.get(notes_key, "")).strip() or None
        entries.append(
            {
                "plot_id": plot_id,
                "harvest_date": harvest_date,
                "weight_grams": grams,
                "notes": notes,
            }
        )

    if entries:
        await plot_harvest_service.create_harvests_batch(
            db, tenant_id=current_user.active_tenant_id, entries=entries
        )
        await db.commit()

    return RedirectResponse(
        f"/harvests/?msg={quote_plus(_('Cosecha registrada correctamente'))}",
        status_code=303,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Edit harvest — GET form
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/harvests/{harvest_id}/edit", response_class=HTMLResponse)
async def edit_harvest_form(
    request: Request,
    harvest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    harvest = await plot_harvest_service.get_harvest(
        db, harvest_id=harvest_id, tenant_id=current_user.active_tenant_id
    )
    if harvest is None:
        return RedirectResponse(
            f"/harvests/?msg={quote_plus(_('Cosecha no encontrada'))}",
            status_code=303,
        )
    plots = await list_plots(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "produccion/form_bancal_edit.html",
        {
            "request": request,
            "plots": plots,
            "harvest": harvest,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Edit harvest — POST submit
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/harvests/{harvest_id}/edit", response_class=RedirectResponse)
async def update_harvest(
    request: Request,
    harvest_id: int,
    harvest_date: str = Form(...),
    weight_grams: str = Form(...),
    notes: str = Form(default=""),
    plot_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    harvest = await plot_harvest_service.get_harvest(
        db, harvest_id=harvest_id, tenant_id=current_user.active_tenant_id
    )
    if harvest is None:
        return RedirectResponse(
            f"/harvests/?msg={quote_plus(_('Cosecha no encontrada'))}",
            status_code=303,
        )

    try:
        parsed_date = datetime.date.fromisoformat(harvest_date)
        parsed_grams = _parse_eu_float(weight_grams)
    except (ValueError, TypeError):
        return RedirectResponse(
            f"/harvests/{harvest_id}/edit?msg={quote_plus(_('Datos inválidos'))}",
            status_code=303,
        )

    await plot_harvest_service.update_harvest(
        db,
        harvest_id=harvest_id,
        tenant_id=current_user.active_tenant_id,
        harvest_date=parsed_date,
        weight_grams=parsed_grams,
        notes=notes.strip() or None,
    )
    await db.commit()
    return RedirectResponse(
        f"/harvests/?msg={quote_plus(_('Cosecha actualizada correctamente'))}",
        status_code=303,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Delete harvest — POST
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/harvests/{harvest_id}/delete", response_class=RedirectResponse)
async def delete_harvest(
    harvest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    await plot_harvest_service.delete_harvest(
        db, harvest_id=harvest_id, tenant_id=current_user.active_tenant_id
    )
    await db.commit()
    return RedirectResponse(
        f"/harvests/?msg={quote_plus(_('Cosecha eliminada'))}",
        status_code=303,
    )
