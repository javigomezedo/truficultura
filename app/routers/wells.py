from __future__ import annotations

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
from app.schemas.well import WellCreate, WellUpdate
from app.services.wells_service import (
    create_well as create_service,
    delete_well as delete_service,
    get_well as get_service,
    get_wells_list_context,
    get_well_expenses_for_plot,
    update_well as update_service,
)

router = APIRouter(prefix="/wells", tags=["wells"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    year: Optional[str] = Query(default=None),
    plot_id: Optional[int] = Query(default=None),
    msg: Optional[str] = None,
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
):
    year_int = int(year) if year else None
    context = await get_wells_list_context(
        db,
        current_user.active_tenant_id,
        year=year_int,
        plot_id=plot_id,
        sort_by=sort or "date",
        sort_order=order if order in ("asc", "desc") else "desc",
    )
    return templates.TemplateResponse(
        request,
        "pozos/list.html",
        {"request": request, **context, "msg": msg},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    from app.services.wells_service import _get_all_plots

    plots = await _get_all_plots(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "pozos/form.html",
        {"request": request, "record": None, "plots": plots, "action": "/wells/"},
    )


@router.post("/", response_class=RedirectResponse)
async def create_view(
    request: Request,
    plot_id: int = Form(...),
    date: datetime.date = Form(...),
    wells_per_plant: int = Form(...),
    expense_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = WellCreate(
        plot_id=plot_id,
        date=date,
        wells_per_plant=wells_per_plant,
        expense_id=expense_id if expense_id else None,
        notes=notes or None,
    )
    await create_service(db, current_user.active_tenant_id, data)
    return RedirectResponse(
        url=f"/wells/?msg={quote_plus(_('Pozo registrado correctamente'))}",
        status_code=303,
    )


@router.get("/{well_id}/edit", response_class=HTMLResponse)
async def edit_form(
    request: Request,
    well_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    from app.services.wells_service import _get_all_plots

    record = await get_service(db, well_id, current_user.active_tenant_id)
    if record is None:
        return RedirectResponse(
            url=f"/wells/?msg={quote_plus(_('Registro no encontrado'))}",
            status_code=303,
        )
    plots = await _get_all_plots(db, current_user.active_tenant_id)
    expenses = await get_well_expenses_for_plot(db, current_user.active_tenant_id, record.plot_id)
    return templates.TemplateResponse(
        request,
        "pozos/form.html",
        {
            "request": request,
            "record": record,
            "plots": plots,
            "expenses": expenses,
            "action": f"/wells/{well_id}/edit",
        },
    )


@router.post("/{well_id}/edit", response_class=RedirectResponse)
async def update_view(
    request: Request,
    well_id: int,
    plot_id: int = Form(...),
    date: datetime.date = Form(...),
    wells_per_plant: int = Form(...),
    expense_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    record = await get_service(db, well_id, current_user.active_tenant_id)
    if record is None:
        return RedirectResponse(
            url=f"/wells/?msg={quote_plus(_('Registro no encontrado'))}",
            status_code=303,
        )
    data = WellUpdate(
        plot_id=plot_id,
        date=date,
        wells_per_plant=wells_per_plant,
        expense_id=expense_id if expense_id else None,
        notes=notes or None,
    )
    await update_service(db, record, data)
    return RedirectResponse(
        url=f"/wells/?msg={quote_plus(_('Pozo actualizado correctamente'))}",
        status_code=303,
    )


@router.post("/{well_id}/delete", response_class=RedirectResponse)
async def delete_view(
    request: Request,
    well_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    await delete_service(db, well_id, current_user.active_tenant_id)
    return RedirectResponse(
        url=f"/wells/?msg={quote_plus(_('Pozo eliminado correctamente'))}",
        status_code=303,
    )


@router.get("/expenses-for-plot/{plot_id}", response_class=JSONResponse)
async def expenses_for_plot(
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    expenses = await get_well_expenses_for_plot(db, current_user.active_tenant_id, plot_id)
    return [
        {
            "id": e.id,
            "description": e.description,
            "date": e.date.isoformat(),
            "amount": e.amount,
        }
        for e in expenses
    ]
