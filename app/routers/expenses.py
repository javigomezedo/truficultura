import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.expenses_service import (
    create_expense as create_expense_service,
    delete_expense as delete_expense_service,
    get_expense,
    get_expenses_list_context,
    list_plots,
    update_expense as update_expense_service,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_expenses(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: Optional[int] = None,
    msg: Optional[str] = None,
):
    context = await get_expenses_list_context(db, year)

    return templates.TemplateResponse(
        "gastos/list.html",
        {
            "request": request,
            **context,
            "msg": msg,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_expense_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    plots = await list_plots(db)
    return templates.TemplateResponse(
        "gastos/form.html",
        {
            "request": request,
            "expense": None,
            "plots": plots,
            "action": "/expenses/",
            "method": "post",
        },
    )


@router.post("/", response_class=RedirectResponse)
async def create_expense(
    date: datetime.date = Form(...),
    description: str = Form(...),
    person: str = Form(""),
    plot_id: Optional[int] = Form(None),
    amount: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    await create_expense_service(
        db,
        date=date,
        description=description,
        person=person,
        plot_id=plot_id,
        amount=amount,
    )
    return RedirectResponse(
        url="/expenses/?msg=Gasto+registrado+correctamente", status_code=303
    )


@router.get("/{expense_id}/edit", response_class=HTMLResponse)
async def edit_expense_form(
    request: Request,
    expense_id: int,
    db: AsyncSession = Depends(get_db),
):
    expense = await get_expense(db, expense_id)
    if expense is None:
        return RedirectResponse(url="/expenses/?msg=Gasto+no+encontrado", status_code=303)

    plots = await list_plots(db)

    return templates.TemplateResponse(
        "gastos/form.html",
        {
            "request": request,
            "expense": expense,
            "plots": plots,
            "action": f"/expenses/{expense_id}",
            "method": "post",
        },
    )


@router.post("/{expense_id}", response_class=RedirectResponse)
async def update_expense(
    expense_id: int,
    date: datetime.date = Form(...),
    description: str = Form(...),
    person: str = Form(""),
    plot_id: Optional[int] = Form(None),
    amount: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    obj = await get_expense(db, expense_id)
    if obj is None:
        return RedirectResponse(url="/expenses/?msg=Gasto+no+encontrado", status_code=303)

    await update_expense_service(
        db,
        obj,
        date=date,
        description=description,
        person=person,
        plot_id=plot_id,
        amount=amount,
    )
    return RedirectResponse(
        url="/expenses/?msg=Gasto+actualizado+correctamente", status_code=303
    )


@router.post("/{expense_id}/delete", response_class=RedirectResponse)
async def delete_expense(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
):
    obj = await get_expense(db, expense_id)
    if obj:
        await delete_expense_service(db, obj)
    return RedirectResponse(
        url="/expenses/?msg=Gasto+eliminado+correctamente", status_code=303
    )
