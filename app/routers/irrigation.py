import datetime
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.i18n import _
from app.models.user import User
from app.schemas.irrigation import IrrigationCreate, IrrigationUpdate
from app.services.irrigation_service import (
    create_irrigation_record as create_service,
    create_irrigation_records_bulk as create_bulk_service,
    delete_irrigation_record as delete_service,
    get_irrigation_list_context,
    get_irrigation_record,
    get_riego_expenses_for_plot,
    get_riego_expenses_for_plots,
    update_irrigation_record as update_service,
)
from app.services.water_balance_service import simulate_irrigation

router = APIRouter(prefix="/irrigation", tags=["irrigation"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/simular", response_class=JSONResponse)
async def simulate_view(
    plot_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    sim = await simulate_irrigation(db, current_user.active_tenant_id, plot_id, datetime.date.today())
    if sim is None:
        return JSONResponse(
            status_code=404,
            content={"detail": _("Parcela no encontrada")},
        )
    return sim


@router.get("/", response_class=HTMLResponse)
async def list_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    year: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    msg: Optional[str] = None,
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
):
    year_int = int(year) if year else None
    plot_id_int = int(plot_id) if plot_id else None
    context = await get_irrigation_list_context(
        db,
        current_user.active_tenant_id,
        year=year_int,
        plot_id=plot_id_int,
        sort_by=sort or "date",
        sort_order=order if order in ("asc", "desc") else "desc",
    )
    return templates.TemplateResponse(
        request,
        "riego/list.html",
        {"request": request, **context, "msg": msg, "today": datetime.date.today().isoformat()},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    from app.services.irrigation_service import _get_irrigable_plots

    plots = await _get_irrigable_plots(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "riego/form.html",
        {"request": request, "record": None, "plots": plots, "action": "/irrigation/"},
    )


@router.post("/", response_class=RedirectResponse)
async def create_view(
    request: Request,
    plot_id: int = Form(...),
    date: datetime.date = Form(...),
    water_m3: float = Form(...),
    expense_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = IrrigationCreate(
        plot_id=plot_id,
        date=date,
        water_m3=water_m3,
        expense_id=expense_id if expense_id else None,
        notes=notes or None,
    )
    await create_service(db, current_user.active_tenant_id, data, acting_user_id=current_user.id)
    return RedirectResponse(
        url=f"/irrigation/?msg={quote_plus(_('Riego registrado correctamente'))}",
        status_code=303,
    )


@router.get("/bulk-new", response_class=HTMLResponse)
async def bulk_new_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    from app.services.irrigation_service import _get_irrigable_plots

    plots = await _get_irrigable_plots(db, current_user.active_tenant_id)
    expenses_by_plot = await get_riego_expenses_for_plots(
        db, current_user.active_tenant_id, [p.id for p in plots]
    )
    return templates.TemplateResponse(
        request,
        "riego/bulk_form.html",
        {
            "request": request,
            "plots": plots,
            "expenses_by_plot": expenses_by_plot,
            "today": datetime.date.today().isoformat(),
        },
    )


@router.post("/bulk", response_class=RedirectResponse)
async def bulk_create_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    form = await request.form()
    plot_ids = form.getlist("plot_id")
    dates = form.getlist("date")
    water_m3s = form.getlist("water_m3")
    expense_ids = form.getlist("expense_id")
    notes_list = form.getlist("notes")

    items = []
    for i, pid in enumerate(plot_ids):
        raw_water = water_m3s[i] if i < len(water_m3s) else ""
        if not raw_water or raw_water.strip() == "":
            continue
        try:
            water_val = float(raw_water.replace(",", "."))
        except ValueError:
            continue
        if water_val <= 0:
            continue
        raw_date = dates[i].strip() if i < len(dates) else ""
        try:
            date_val = datetime.date.fromisoformat(raw_date)
        except ValueError:
            continue
        notes_val = notes_list[i].strip() if i < len(notes_list) else ""
        raw_eid = expense_ids[i].strip() if i < len(expense_ids) else ""
        expense_id_val = int(raw_eid) if raw_eid else None
        items.append(
            IrrigationCreate(
                plot_id=int(pid),
                date=date_val,
                water_m3=water_val,
                expense_id=expense_id_val,
                notes=notes_val or None,
            )
        )

    if not items:
        return RedirectResponse(
            url=f"/irrigation/?msg={quote_plus(_('No se introdujo ningún dato de riego'))}",
            status_code=303,
        )

    await create_bulk_service(db, current_user.active_tenant_id, items, acting_user_id=current_user.id)

    msg = _("%(n)s registros de riego guardados correctamente") % {"n": len(items)}
    return RedirectResponse(
        url=f"/irrigation/?msg={quote_plus(msg)}",
        status_code=303,
    )


@router.get("/{record_id}/edit", response_class=HTMLResponse)
async def edit_form(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    from app.services.irrigation_service import _get_irrigable_plots

    record = await get_irrigation_record(db, record_id, current_user.active_tenant_id)
    if record is None:
        return RedirectResponse(
            url=f"/irrigation/?msg={quote_plus(_('Registro no encontrado'))}",
            status_code=303,
        )
    plots = await _get_irrigable_plots(db, current_user.active_tenant_id)
    expenses = await get_riego_expenses_for_plot(db, current_user.active_tenant_id, record.plot_id)
    return templates.TemplateResponse(
        request,
        "riego/form.html",
        {
            "request": request,
            "record": record,
            "plots": plots,
            "expenses": expenses,
            "action": f"/irrigation/{record_id}/edit",
        },
    )


@router.post("/{record_id}/edit", response_class=RedirectResponse)
async def update_view(
    request: Request,
    record_id: int,
    plot_id: int = Form(...),
    date: datetime.date = Form(...),
    water_m3: float = Form(...),
    expense_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    record = await get_irrigation_record(db, record_id, current_user.active_tenant_id)
    if record is None:
        return RedirectResponse(
            url=f"/irrigation/?msg={quote_plus(_('Registro no encontrado'))}",
            status_code=303,
        )
    data = IrrigationUpdate(
        plot_id=plot_id,
        date=date,
        water_m3=water_m3,
        expense_id=expense_id if expense_id else None,
        notes=notes or None,
    )
    await update_service(db, record, data, acting_user_id=current_user.id)
    return RedirectResponse(
        url=f"/irrigation/?msg={quote_plus(_('Riego actualizado correctamente'))}",
        status_code=303,
    )


@router.post("/{record_id}/delete", response_class=RedirectResponse)
async def delete_view(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    await delete_service(db, record_id, current_user.active_tenant_id)
    return RedirectResponse(
        url=f"/irrigation/?msg={quote_plus(_('Riego eliminado correctamente'))}",
        status_code=303,
    )


@router.get("/expenses-for-plot/{plot_id}", response_class=JSONResponse)
async def expenses_for_plot(
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    expenses = await get_riego_expenses_for_plot(db, current_user.active_tenant_id, plot_id)
    return [
        {
            "id": e.id,
            "description": e.description,
            "date": e.date.isoformat(),
            "amount": e.amount,
        }
        for e in expenses
    ]
