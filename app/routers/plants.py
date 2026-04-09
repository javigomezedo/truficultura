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
from app.utils import campaign_year, format_sparse_row_config, parse_row_config

router = APIRouter(tags=["plants"])
templates = Jinja2Templates(directory="app/templates")


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


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

    selected = _parse_optional_int(campaign)
    ctx = await plants_service.get_plot_map_context(
        db, plot, user_id=current_user.id, selected_campaign=selected
    )

    year_events = await truffle_events_service.list_events(
        db,
        user_id=current_user.id,
        campaign_year=None,
        plot_id=plot_id,
        include_undone=True,
        limit=2000,
    )
    campaign_years = sorted(
        {
            campaign_year(e.created_at.date())
            for e in year_events
            if getattr(e, "created_at", None) is not None
        },
        reverse=True,
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
            "campaign_years": campaign_years,
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

    # Build current row configuration string from existing plants
    all_plants = await plants_service.list_plants(db, plot_id, current_user.id)
    row_columns: list[list[int]] = []
    if all_plants:
        by_row: dict[int, list[int]] = {}
        for p in all_plants:
            by_row.setdefault(p.row_order, []).append(p.visual_col)
        row_columns = [sorted(by_row[idx]) for idx in sorted(by_row)]

    return templates.TemplateResponse(
        request,
        "parcelas/mapa_configure.html",
        {
            "request": request,
            "plot": plot,
            "has_events": has_events,
            "row_config_value": format_sparse_row_config(row_columns)
            if row_columns
            else "",
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
    """row_config supports only sparse row format (e.g. A:2-5,8; B:1,3,4)."""
    plot = await get_plot(db, plot_id, current_user.id)
    if plot is None:
        return RedirectResponse("/plots/?msg=Parcela+no+encontrada", status_code=303)

    try:
        row_columns = parse_row_config(row_config)
    except ValueError as exc:
        return RedirectResponse(
            f"/plots/{plot_id}/map/configure?msg={str(exc).replace(' ', '+')}",
            status_code=303,
        )

    try:
        await plants_service.configure_plot_map(
            db, plot, user_id=current_user.id, row_columns=row_columns
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
    estimated_weight_grams: float = Form(default=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    plant = await plants_service.get_plant(db, plant_id, current_user.id)
    if plant is None or plant.plot_id != plot_id:
        return RedirectResponse(
            f"/plots/{plot_id}/map?msg=Planta+no+encontrada", status_code=303
        )

    weight = max(0.1, min(float(estimated_weight_grams), 5000.0))

    await truffle_events_service.create_event(
        db,
        plant_id=plant_id,
        plot_id=plot_id,
        user_id=current_user.id,
        estimated_weight_grams=weight,
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

    msg = "Último+registro+eliminado" if undone else "No+hay+registro+para+deshacer"
    if campaign:
        target = f"/plots/{plot_id}/map?campaign={campaign}&msg={msg}"
    else:
        target = f"/plots/{plot_id}/map?msg={msg}"
    return RedirectResponse(target, status_code=303)


@router.post("/truffles/{event_id}/delete", response_class=RedirectResponse)
async def delete_truffle_event_from_list(
    request: Request,
    event_id: int,
    camp: Optional[str] = Form(default=None),
    plot_id: Optional[str] = Form(default=None),
    plant_id: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    deleted = await truffle_events_service.delete_event(
        db,
        event_id=event_id,
        user_id=current_user.id,
    )

    params: list[str] = []
    if camp:
        params.append(f"camp={camp}")
    if plot_id:
        params.append(f"plot_id={plot_id}")
    if plant_id:
        params.append(f"plant_id={plant_id}")

    msg = (
        "msg=Registro+de+trufa+eliminado"
        if deleted
        else "msg=No+se+ha+encontrado+el+registro"
    )
    query = "&".join(params + [msg]) if params else msg
    return RedirectResponse(f"/truffles/?{query}", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Truffle events list
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/truffles/", response_class=HTMLResponse)
async def list_truffle_events(
    request: Request,
    camp: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    plant_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    camp_int = _parse_optional_int(camp)
    plot_id_int = _parse_optional_int(plot_id)
    plant_id_int = _parse_optional_int(plant_id)
    plots = await list_plots(db, current_user.id)
    plants_for_filter = (
        await plants_service.list_plants(db, plot_id_int, current_user.id)
        if plot_id_int is not None
        else []
    )

    year_events = await truffle_events_service.list_events(
        db,
        user_id=current_user.id,
        campaign_year=None,
        plot_id=plot_id_int,
        plant_id=plant_id_int,
        include_undone=False,
        limit=2000,
    )
    campaign_years = sorted(
        {
            campaign_year(e.created_at.date())
            for e in year_events
            if getattr(e, "created_at", None) is not None
        },
        reverse=True,
    )

    events = await truffle_events_service.list_events(
        db,
        user_id=current_user.id,
        campaign_year=camp_int,
        plot_id=plot_id_int,
        plant_id=plant_id_int,
        include_undone=False,
    )

    if camp_int is not None:
        historical_active_events = await truffle_events_service.list_events(
            db,
            user_id=current_user.id,
            campaign_year=None,
            plot_id=plot_id_int,
            plant_id=plant_id_int,
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
            "plants_for_filter": plants_for_filter,
            "selected_campaign": camp_int,
            "selected_plot_id": plot_id_int,
            "selected_plant_id": plant_id_int,
            "campaign_years": campaign_years,
            "summary_rows": summary_rows,
        },
    )


@router.get("/plots/{plot_id}/qr-pdf")
async def download_plot_qr_pdf(
    request: Request,
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Generate a PDF with one QR code per plant for the current user's plot."""
    import io

    import qrcode
    from fpdf import FPDF

    from app.routers.scan import sign_plant_token

    plot = await get_plot(db, plot_id, current_user.id)
    if plot is None:
        return RedirectResponse("/plots/?msg=Parcela+no+encontrada", status_code=303)

    plants = await plants_service.list_plants(db, plot_id, current_user.id)
    if not plants:
        return RedirectResponse(
            "/plots/?msg=La+parcela+no+tiene+plantas+configuradas",
            status_code=303,
        )

    base_url = str(request.base_url).rstrip("/")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)

    page_w = 210.0
    qr_size = 140.0

    for plant in plants:
        pdf.add_page()
        scan_url = f"{base_url}/scan/{sign_plant_token(plant.id)}"

        img = qrcode.make(scan_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        qr_x = (page_w - qr_size) / 2
        qr_y = 34.0
        pdf.image(buf, x=qr_x, y=qr_y, w=qr_size, h=qr_size)

        pdf.set_font("Helvetica", "B", 24)
        pdf.set_xy(0, qr_y + qr_size + 14)
        pdf.cell(page_w, 12, plant.label, align="C")

        pdf.set_font("Helvetica", "", 12)
        pdf.set_xy(0, qr_y + qr_size + 28)
        pdf.cell(page_w, 8, plot.name, align="C")

    pdf_bytes = pdf.output()
    filename = f"qr_{plot.name.replace(' ', '_')}_{current_user.id}.pdf"

    from fastapi.responses import Response

    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
