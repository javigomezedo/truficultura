import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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
    year: Optional[str] = Query(default=None),
    msg: Optional[str] = None,
):
    year_int = int(year) if year else None
    context = await get_incomes_list_context(db, year_int)

    return templates.TemplateResponse(
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
):
    plots = await list_plots(db)
    return templates.TemplateResponse(
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
    date: datetime.date = Form(...),
    plot_id: Optional[int] = Form(None),
    amount_kg: float = Form(0.0),
    category: str = Form(""),
    euros_per_kg: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    await create_income_service(
        db,
        date=date,
        plot_id=plot_id,
        amount_kg=amount_kg,
        category=category,
        euros_per_kg=euros_per_kg,
    )
    return RedirectResponse(
        url="/incomes/?msg=Ingreso+registrado+correctamente", status_code=303
    )


@router.get("/{income_id}/edit", response_class=HTMLResponse)
async def edit_income_form(
    request: Request,
    income_id: int,
    db: AsyncSession = Depends(get_db),
):
    income = await get_income(db, income_id)
    if income is None:
        return RedirectResponse(
            url="/incomes/?msg=Ingreso+no+encontrado", status_code=303
        )

    plots = await list_plots(db)

    return templates.TemplateResponse(
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
    income_id: int,
    date: datetime.date = Form(...),
    plot_id: Optional[int] = Form(None),
    amount_kg: float = Form(0.0),
    category: str = Form(""),
    euros_per_kg: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    obj = await get_income(db, income_id)
    if obj is None:
        return RedirectResponse(
            url="/incomes/?msg=Ingreso+no+encontrado", status_code=303
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
        url="/incomes/?msg=Ingreso+actualizado+correctamente", status_code=303
    )


@router.post("/{income_id}/delete", response_class=RedirectResponse)
async def delete_income(
    income_id: int,
    db: AsyncSession = Depends(get_db),
):
    obj = await get_income(db, income_id)
    if obj:
        await delete_income_service(db, obj)
    return RedirectResponse(
        url="/incomes/?msg=Ingreso+eliminado+correctamente", status_code=303
    )
