from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.i18n import _
from app.models.expense import EXPENSE_CATEGORIES
from app.models.recurring_expense import FREQUENCIES
from app.models.user import User
from app.services.recurring_expenses_service import (
    create_recurring_expense as create_recurring_expense_service,
    delete_recurring_expense as delete_recurring_expense_service,
    get_recurring_expense,
    list_plots,
    list_recurring_expenses,
    toggle_recurring_expense as toggle_recurring_expense_service,
    update_recurring_expense as update_recurring_expense_service,
)

router = APIRouter(prefix="/recurring-expenses", tags=["recurring-expenses"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_recurring_expenses_view(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
    msg: Optional[str] = Query(default=None),
):
    items = await list_recurring_expenses(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "gastos/recurrentes/list.html",
        {
            "request": request,
            "recurring_expenses": items,
            "msg": msg,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_recurring_expense_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    plots = await list_plots(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "gastos/recurrentes/form.html",
        {
            "request": request,
            "recurring_expense": None,
            "plots": plots,
            "categories": EXPENSE_CATEGORIES,
            "frequencies": FREQUENCIES,
            "action": "/recurring-expenses/",
            "method": "post",
        },
    )


@router.post("/", response_class=RedirectResponse)
async def create_recurring_expense(
    request: Request,
    description: str = Form(...),
    amount: float = Form(0.0),
    category: Optional[str] = Form(None),
    plot_id: Optional[int] = Form(None),
    person: str = Form(""),
    frequency: str = Form("monthly"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    await create_recurring_expense_service(
        db,
        tenant_id=current_user.active_tenant_id,
        description=description,
        amount=amount,
        category=category,
        plot_id=plot_id,
        person=person,
        frequency=frequency,
    )
    return RedirectResponse(
        url=f"/recurring-expenses/?msg={quote_plus(_('Gasto recurrente creado correctamente'))}",
        status_code=303,
    )


@router.get("/{recurring_expense_id}/edit", response_class=HTMLResponse)
async def edit_recurring_expense_form(
    request: Request,
    recurring_expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    obj = await get_recurring_expense(db, recurring_expense_id, current_user.active_tenant_id)
    if obj is None:
        return RedirectResponse(
            url=f"/recurring-expenses/?msg={quote_plus(_('Gasto recurrente no encontrado'))}",
            status_code=303,
        )
    plots = await list_plots(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "gastos/recurrentes/form.html",
        {
            "request": request,
            "recurring_expense": obj,
            "plots": plots,
            "categories": EXPENSE_CATEGORIES,
            "frequencies": FREQUENCIES,
            "action": f"/recurring-expenses/{recurring_expense_id}",
            "method": "post",
        },
    )


@router.post("/{recurring_expense_id}", response_class=RedirectResponse)
async def update_recurring_expense(
    request: Request,
    recurring_expense_id: int,
    description: str = Form(...),
    amount: float = Form(0.0),
    category: Optional[str] = Form(None),
    plot_id: Optional[int] = Form(None),
    person: str = Form(""),
    frequency: str = Form("monthly"),
    is_active: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    obj = await get_recurring_expense(db, recurring_expense_id, current_user.active_tenant_id)
    if obj is None:
        return RedirectResponse(
            url=f"/recurring-expenses/?msg={quote_plus(_('Gasto recurrente no encontrado'))}",
            status_code=303,
        )
    await update_recurring_expense_service(
        db,
        obj,
        description=description,
        amount=amount,
        category=category,
        plot_id=plot_id,
        person=person,
        frequency=frequency,
        is_active=is_active,
    )
    return RedirectResponse(
        url=f"/recurring-expenses/?msg={quote_plus(_('Gasto recurrente actualizado correctamente'))}",
        status_code=303,
    )


@router.post("/{recurring_expense_id}/delete", response_class=RedirectResponse)
async def delete_recurring_expense(
    request: Request,
    recurring_expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    obj = await get_recurring_expense(db, recurring_expense_id, current_user.active_tenant_id)
    if obj:
        await delete_recurring_expense_service(db, obj)
    return RedirectResponse(
        url=f"/recurring-expenses/?msg={quote_plus(_('Gasto recurrente eliminado correctamente'))}",
        status_code=303,
    )


@router.post("/{recurring_expense_id}/toggle", response_class=RedirectResponse)
async def toggle_recurring_expense(
    request: Request,
    recurring_expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    obj = await get_recurring_expense(db, recurring_expense_id, current_user.active_tenant_id)
    if obj is None:
        return RedirectResponse(
            url=f"/recurring-expenses/?msg={quote_plus(_('Gasto recurrente no encontrado'))}",
            status_code=303,
        )
    await toggle_recurring_expense_service(db, obj)
    return RedirectResponse(
        url=f"/recurring-expenses/?msg={quote_plus(_('Estado actualizado correctamente'))}",
        status_code=303,
    )
