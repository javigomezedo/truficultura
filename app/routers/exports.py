from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.models.user import User
from app.services.export_service import (
    export_expenses_csv,
    export_incomes_csv,
    export_irrigation_csv,
    export_plots_csv,
    export_wells_csv,
)

router = APIRouter(prefix="/export", tags=["export"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def export_page(
    request: Request,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "exports/index.html",
        {"request": request},
    )


@router.get("/plots.csv")
async def download_plots(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    data = await export_plots_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=parcelas.csv"},
    )


@router.get("/expenses.csv")
async def download_expenses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    data = await export_expenses_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=gastos.csv"},
    )


@router.get("/incomes.csv")
async def download_incomes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    data = await export_incomes_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=ingresos.csv"},
    )


@router.get("/irrigation.csv")
async def download_irrigation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    data = await export_irrigation_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=riego.csv"},
    )


@router.get("/wells.csv")
async def download_wells(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    data = await export_wells_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=pozos.csv"},
    )
