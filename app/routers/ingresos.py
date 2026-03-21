import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.ingresos_service import (
    create_ingreso as create_ingreso_service,
    delete_ingreso as delete_ingreso_service,
    get_ingreso,
    get_ingresos_list_context,
    list_parcelas,
    update_ingreso as update_ingreso_service,
)

router = APIRouter(prefix="/ingresos", tags=["ingresos"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_ingresos(
    request: Request,
    db: AsyncSession = Depends(get_db),
    year: Optional[int] = None,
    msg: Optional[str] = None,
):
    context = await get_ingresos_list_context(db, year)

    return templates.TemplateResponse(
        "ingresos/list.html",
        {
            "request": request,
            **context,
            "msg": msg,
        },
    )


@router.get("/nuevo", response_class=HTMLResponse)
async def new_ingreso_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    parcelas = await list_parcelas(db)
    return templates.TemplateResponse(
        "ingresos/form.html",
        {
            "request": request,
            "ingreso": None,
            "parcelas": parcelas,
            "action": "/ingresos/",
            "method": "post",
        },
    )


@router.post("/", response_class=RedirectResponse)
async def create_ingreso(
    fecha: datetime.date = Form(...),
    parcela_id: Optional[int] = Form(None),
    cantidad_kg: float = Form(0.0),
    categoria: str = Form(""),
    euros_kg: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    await create_ingreso_service(
        db,
        fecha=fecha,
        parcela_id=parcela_id,
        cantidad_kg=cantidad_kg,
        categoria=categoria,
        euros_kg=euros_kg,
    )
    return RedirectResponse(
        url="/ingresos/?msg=Ingreso+registrado+correctamente", status_code=303
    )


@router.get("/{ingreso_id}/editar", response_class=HTMLResponse)
async def edit_ingreso_form(
    request: Request,
    ingreso_id: int,
    db: AsyncSession = Depends(get_db),
):
    ingreso = await get_ingreso(db, ingreso_id)
    if ingreso is None:
        return RedirectResponse(
            url="/ingresos/?msg=Ingreso+no+encontrado", status_code=303
        )

    parcelas = await list_parcelas(db)

    return templates.TemplateResponse(
        "ingresos/form.html",
        {
            "request": request,
            "ingreso": ingreso,
            "parcelas": parcelas,
            "action": f"/ingresos/{ingreso_id}",
            "method": "post",
        },
    )


@router.post("/{ingreso_id}", response_class=RedirectResponse)
async def update_ingreso(
    ingreso_id: int,
    fecha: datetime.date = Form(...),
    parcela_id: Optional[int] = Form(None),
    cantidad_kg: float = Form(0.0),
    categoria: str = Form(""),
    euros_kg: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    obj = await get_ingreso(db, ingreso_id)
    if obj is None:
        return RedirectResponse(
            url="/ingresos/?msg=Ingreso+no+encontrado", status_code=303
        )

    await update_ingreso_service(
        db,
        obj,
        fecha=fecha,
        parcela_id=parcela_id,
        cantidad_kg=cantidad_kg,
        categoria=categoria,
        euros_kg=euros_kg,
    )
    return RedirectResponse(
        url="/ingresos/?msg=Ingreso+actualizado+correctamente", status_code=303
    )


@router.post("/{ingreso_id}/eliminar", response_class=RedirectResponse)
async def delete_ingreso(
    ingreso_id: int,
    db: AsyncSession = Depends(get_db),
):
    obj = await get_ingreso(db, ingreso_id)
    if obj:
        await delete_ingreso_service(db, obj)
    return RedirectResponse(
        url="/ingresos/?msg=Ingreso+eliminado+correctamente", status_code=303
    )
