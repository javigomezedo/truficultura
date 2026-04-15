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
from app.services.incomes_service import (
    create_income as create_income_service,
    delete_income as delete_income_service,
    get_income,
    get_incomes_list_context,
    list_plots,
    update_income as update_income_service,
)

router = APIRouter(prefix="/incomes", tags=["incomes"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_incomes(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    year: Optional[str] = Query(default=None),
    msg: Optional[str] = None,
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
):
    year_int = int(year) if year else None
    context = await get_incomes_list_context(
        db,
        year_int,
        current_user.id,
        sort_by=sort or "date",
        sort_order=order if order in ("asc", "desc") else "desc",
    )

    return templates.TemplateResponse(
        request,
        "ingresos/list.html",
        {
            "request": request,
            **context,
            "msg": msg,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_income_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    plots = await list_plots(db, current_user.id)
    return templates.TemplateResponse(
        request,
        "ingresos/form.html",
        {
            "request": request,
            "income": None,
            "plots": plots,
            "action": "/incomes/",
            "method": "post",
        },
    )


@router.post("/", response_class=RedirectResponse)
async def create_income(
    request: Request,
    date: datetime.date = Form(...),
    plot_id: Optional[int] = Form(None),
    amount_kg: float = Form(0.0),
    category: str = Form(""),
    euros_per_kg: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await create_income_service(
        db,
        user_id=current_user.id,
        date=date,
        plot_id=plot_id,
        amount_kg=amount_kg,
        category=category,
        euros_per_kg=euros_per_kg,
    )
    return RedirectResponse(
        url=f"/incomes/?msg={quote_plus(_('Ingreso registrado correctamente'))}",
        status_code=303,
    )


@router.get("/{income_id}/edit", response_class=HTMLResponse)
async def edit_income_form(
    request: Request,
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    income = await get_income(db, income_id, current_user.id)
    if income is None:
        return RedirectResponse(
            url=f"/incomes/?msg={quote_plus(_('Ingreso no encontrado'))}",
            status_code=303,
        )

    plots = await list_plots(db, current_user.id)

    return templates.TemplateResponse(
        request,
        "ingresos/form.html",
        {
            "request": request,
            "income": income,
            "plots": plots,
            "action": f"/incomes/{income_id}",
            "method": "post",
        },
    )


@router.post("/{income_id}", response_class=RedirectResponse)
async def update_income(
    request: Request,
    income_id: int,
    date: datetime.date = Form(...),
    plot_id: Optional[int] = Form(None),
    amount_kg: float = Form(0.0),
    category: str = Form(""),
    euros_per_kg: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    obj = await get_income(db, income_id, current_user.id)
    if obj is None:
        return RedirectResponse(
            url=f"/incomes/?msg={quote_plus(_('Ingreso no encontrado'))}",
            status_code=303,
        )

    await update_income_service(
        db,
        obj,
        date=date,
        plot_id=plot_id,
        amount_kg=amount_kg,
        category=category,
        euros_per_kg=euros_per_kg,
    )
    return RedirectResponse(
        url=f"/incomes/?msg={quote_plus(_('Ingreso actualizado correctamente'))}",
        status_code=303,
    )


@router.post("/{income_id}/delete", response_class=RedirectResponse)
async def delete_income(
    request: Request,
    income_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    obj = await get_income(db, income_id, current_user.id)
    if obj:
        await delete_income_service(db, obj)
    return RedirectResponse(
        url=f"/incomes/?msg={quote_plus(_('Ingreso eliminado correctamente'))}",
        status_code=303,
    )
