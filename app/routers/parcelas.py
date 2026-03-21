import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.parcelas_service import (
    create_parcela as create_parcela_service,
    delete_parcela as delete_parcela_service,
    get_parcela,
    list_parcelas as list_parcelas_service,
    update_parcela as update_parcela_service,
)

router = APIRouter(prefix="/parcelas", tags=["parcelas"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_parcelas(
    request: Request,
    db: AsyncSession = Depends(get_db),
    msg: Optional[str] = None,
):
    parcelas = await list_parcelas_service(db)
    return templates.TemplateResponse(
        "parcelas/list.html",
        {"request": request, "parcelas": parcelas, "msg": msg},
    )


@router.get("/nueva", response_class=HTMLResponse)
async def new_parcela_form(request: Request):
    return templates.TemplateResponse(
        "parcelas/form.html",
        {"request": request, "parcela": None, "action": "/parcelas/", "method": "post"},
    )


@router.post("/", response_class=RedirectResponse)
async def create_parcela(
    nombre: str = Form(...),
    poligono: str = Form(""),
    parcela_catastro: str = Form("", alias="parcela"),
    hidrante: str = Form(""),
    sector: str = Form(""),
    n_carrascas: int = Form(0),
    fecha_plantacion: datetime.date = Form(...),
    superficie_ha: Optional[float] = Form(None),
    inicio_produccion: Optional[datetime.date] = Form(None),
    porcentaje: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    await create_parcela_service(
        db,
        nombre=nombre,
        poligono=poligono,
        parcela_catastro=parcela_catastro,
        hidrante=hidrante,
        sector=sector,
        n_carrascas=n_carrascas,
        fecha_plantacion=fecha_plantacion,
        superficie_ha=superficie_ha,
        inicio_produccion=inicio_produccion,
        porcentaje=porcentaje,
    )
    return RedirectResponse(
        url="/parcelas/?msg=Parcela+creada+correctamente", status_code=303
    )


@router.get("/{parcela_id}/editar", response_class=HTMLResponse)
async def edit_parcela_form(
    request: Request,
    parcela_id: int,
    db: AsyncSession = Depends(get_db),
):
    obj = await get_parcela(db, parcela_id)
    if obj is None:
        return RedirectResponse(
            url="/parcelas/?msg=Parcela+no+encontrada", status_code=303
        )
    return templates.TemplateResponse(
        "parcelas/form.html",
        {
            "request": request,
            "parcela": obj,
            "action": f"/parcelas/{parcela_id}",
            "method": "post",
        },
    )


@router.post("/{parcela_id}", response_class=RedirectResponse)
async def update_parcela(
    parcela_id: int,
    nombre: str = Form(...),
    poligono: str = Form(""),
    parcela_catastro: str = Form("", alias="parcela"),
    hidrante: str = Form(""),
    sector: str = Form(""),
    n_carrascas: int = Form(0),
    fecha_plantacion: datetime.date = Form(...),
    superficie_ha: Optional[float] = Form(None),
    inicio_produccion: Optional[datetime.date] = Form(None),
    porcentaje: float = Form(0.0),
    db: AsyncSession = Depends(get_db),
):
    obj = await get_parcela(db, parcela_id)
    if obj is None:
        return RedirectResponse(
            url="/parcelas/?msg=Parcela+no+encontrada", status_code=303
        )

    await update_parcela_service(
        db,
        obj,
        nombre=nombre,
        poligono=poligono,
        parcela_catastro=parcela_catastro,
        hidrante=hidrante,
        sector=sector,
        n_carrascas=n_carrascas,
        fecha_plantacion=fecha_plantacion,
        superficie_ha=superficie_ha,
        inicio_produccion=inicio_produccion,
        porcentaje=porcentaje,
    )
    return RedirectResponse(
        url="/parcelas/?msg=Parcela+actualizada+correctamente", status_code=303
    )


@router.post("/{parcela_id}/eliminar", response_class=RedirectResponse)
async def delete_parcela(
    parcela_id: int,
    db: AsyncSession = Depends(get_db),
):
    obj = await get_parcela(db, parcela_id)
    if obj:
        await delete_parcela_service(db, obj)
    return RedirectResponse(
        url="/parcelas/?msg=Parcela+eliminada+correctamente", status_code=303
    )
