import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.gastos_service import (
    create_gasto as create_gasto_service,
    delete_gasto as delete_gasto_service,
    get_gasto,
    get_gastos_list_context,
    list_parcelas,
    update_gasto as update_gasto_service,
)

router = APIRouter(prefix="/gastos", tags=["gastos"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_gastos(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: Optional[int] = None,
    msg: Optional[str] = None,
):
    context = await get_gastos_list_context(db, year)

    return templates.TemplateResponse(
        "gastos/list.html",
        {
            "request": request,
            **context,
            "msg": msg,
        },
    )


@router.get("/nuevo", response_class=HTMLResponse)
async def new_gasto_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    parcelas = await list_parcelas(db)
    return templates.TemplateResponse(
        "gastos/form.html",
        {
            "request": request,
            "gasto": None,
            "parcelas": parcelas,
            "action": "/gastos/",
            "method": "post",
        },
    )


@router.post("/", response_class=RedirectResponse)
async def create_gasto(
    fecha: datetime.date = Form(...),
    concepto: str = Form(...),
    persona: str = Form(""),
    parcela_id: Optional[int] = Form(None),
    cantidad: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    await create_gasto_service(
        db,
        fecha=fecha,
        concepto=concepto,
        persona=persona,
        parcela_id=parcela_id,
        cantidad=cantidad,
    )
    return RedirectResponse(
        url="/gastos/?msg=Gasto+registrado+correctamente", status_code=303
    )


@router.get("/{gasto_id}/editar", response_class=HTMLResponse)
async def edit_gasto_form(
    request: Request,
    gasto_id: int,
    db: AsyncSession = Depends(get_db),
):
    gasto = await get_gasto(db, gasto_id)
    if gasto is None:
        return RedirectResponse(url="/gastos/?msg=Gasto+no+encontrado", status_code=303)

    parcelas = await list_parcelas(db)

    return templates.TemplateResponse(
        "gastos/form.html",
        {
            "request": request,
            "gasto": gasto,
            "parcelas": parcelas,
            "action": f"/gastos/{gasto_id}",
            "method": "post",
        },
    )


@router.post("/{gasto_id}", response_class=RedirectResponse)
async def update_gasto(
    gasto_id: int,
    fecha: datetime.date = Form(...),
    concepto: str = Form(...),
    persona: str = Form(""),
    parcela_id: Optional[int] = Form(None),
    cantidad: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    obj = await get_gasto(db, gasto_id)
    if obj is None:
        return RedirectResponse(url="/gastos/?msg=Gasto+no+encontrado", status_code=303)

    await update_gasto_service(
        db,
        obj,
        fecha=fecha,
        concepto=concepto,
        persona=persona,
        parcela_id=parcela_id,
        cantidad=cantidad,
    )
    return RedirectResponse(
        url="/gastos/?msg=Gasto+actualizado+correctamente", status_code=303
    )


@router.post("/{gasto_id}/eliminar", response_class=RedirectResponse)
async def delete_gasto(
    gasto_id: int,
    db: AsyncSession = Depends(get_db),
):
    obj = await get_gasto(db, gasto_id)
    if obj:
        await delete_gasto_service(db, obj)
    return RedirectResponse(
        url="/gastos/?msg=Gasto+eliminado+correctamente", status_code=303
    )
