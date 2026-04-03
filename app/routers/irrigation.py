import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.models.user import User
from app.schemas.irrigation import IrrigationCreate, IrrigationUpdate
from app.services.irrigation_service import (
    create_irrigation_record as create_service,
    delete_irrigation_record as delete_service,
    get_irrigation_list_context,
    get_irrigation_record,
    get_riego_expenses_for_plot,
    update_irrigation_record as update_service,
)

router = APIRouter(prefix="/irrigation", tags=["irrigation"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    year: Optional[str] = Query(default=None),
    plot_id: Optional[int] = Query(default=None),
    msg: Optional[str] = None,
):
    year_int = int(year) if year else None
    context = await get_irrigation_list_context(
        db, current_user.id, year=year_int, plot_id=plot_id
    )
    return templates.TemplateResponse(
        request,
        "riego/list.html",
        {"request": request, **context, "msg": msg},
    )


@router.get("/new", response_class=HTMLResponse)
async def new_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    from app.services.irrigation_service import _get_irrigable_plots

    plots = await _get_irrigable_plots(db, current_user.id)
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
    current_user: User = Depends(require_user),
):
    data = IrrigationCreate(
        plot_id=plot_id,
        date=date,
        water_m3=water_m3,
        expense_id=expense_id if expense_id else None,
        notes=notes or None,
    )
    await create_service(db, current_user.id, data)
    return RedirectResponse(
        url="/irrigation/?msg=Riego+registrado+correctamente", status_code=303
    )


@router.get("/{record_id}/edit", response_class=HTMLResponse)
async def edit_form(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    from app.services.irrigation_service import _get_irrigable_plots

    record = await get_irrigation_record(db, record_id, current_user.id)
    if record is None:
        return RedirectResponse(
            url="/irrigation/?msg=Registro+no+encontrado", status_code=303
        )
    plots = await _get_irrigable_plots(db, current_user.id)
    expenses = await get_riego_expenses_for_plot(db, current_user.id, record.plot_id)
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
    current_user: User = Depends(require_user),
):
    record = await get_irrigation_record(db, record_id, current_user.id)
    if record is None:
        return RedirectResponse(
            url="/irrigation/?msg=Registro+no+encontrado", status_code=303
        )
    data = IrrigationUpdate(
        plot_id=plot_id,
        date=date,
        water_m3=water_m3,
        expense_id=expense_id if expense_id else None,
        notes=notes or None,
    )
    await update_service(db, record, data)
    return RedirectResponse(
        url="/irrigation/?msg=Riego+actualizado+correctamente", status_code=303
    )


@router.post("/{record_id}/delete", response_class=RedirectResponse)
async def delete_view(
    request: Request,
    record_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await delete_service(db, record_id, current_user.id)
    return RedirectResponse(
        url="/irrigation/?msg=Riego+eliminado+correctamente", status_code=303
    )


@router.get("/expenses-for-plot/{plot_id}", response_class=JSONResponse)
async def expenses_for_plot(
    plot_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    expenses = await get_riego_expenses_for_plot(db, current_user.id, plot_id)
    return [
        {
            "id": e.id,
            "description": e.description,
            "date": e.date.isoformat(),
            "amount": e.amount,
        }
        for e in expenses
    ]
