from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.models.user import User
from app.services.export_service import (
    export_all_csv_zip,
    export_expenses_csv,
    export_harvests_csv,
    export_incomes_csv,
    export_irrigation_csv,
    export_plot_events_csv,
    export_plots_csv,
    export_presences_csv,
    export_recurring_expenses_csv,
    export_truffles_csv,
    export_wells_csv,
)

router = APIRouter(prefix="/export", tags=["export"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def export_page(
    request: Request,
    current_user: User = Depends(require_subscription),
):
    return templates.TemplateResponse(
        request,
        "exports/index.html",
        {"request": request},
    )


@router.get("/all.zip")
async def download_all_csv_zip(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = await export_all_csv_zip(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=exportacion_csv.zip"},
    )


@router.get("/plots.csv")
async def download_plots(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
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
    current_user: User = Depends(require_subscription),
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
    current_user: User = Depends(require_subscription),
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
    current_user: User = Depends(require_subscription),
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
    current_user: User = Depends(require_subscription),
):
    data = await export_wells_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=pozos.csv"},
    )


@router.get("/truffles.csv")
async def download_truffles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = await export_truffles_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=produccion.csv"},
    )


@router.get("/plot_events.csv")
async def download_plot_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = await export_plot_events_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=labores.csv"},
    )


@router.get("/recurring_expenses.csv")
async def download_recurring_expenses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = await export_recurring_expenses_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=gastos_recurrentes.csv"},
    )


@router.get("/harvests.csv")
async def download_harvests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = await export_harvests_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=cosechas.csv"},
    )


@router.get("/presences.csv")
async def download_presences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    data = await export_presences_csv(db, current_user.id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=presencias.csv"},
    )
