from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.models.user import User
from app.services.import_service import (
    import_all_csv_zip,
    import_expenses_csv,
    import_harvests_csv,
    import_incomes_csv,
    import_irrigation_csv,
    import_plot_events_csv,
    import_plots_csv,
    import_presences_csv,
    import_recurring_expenses_csv,
    import_truffles_csv,
    import_wells_csv,
)

router = APIRouter(prefix="/import", tags=["import"])
templates = Jinja2Templates(directory="app/templates")


def _summarize_zip_import(imported_by_file: dict[str, int]) -> list[str]:
    labels = {
        "parcelas.csv": "parcelas",
        "gastos.csv": "gastos",
        "ingresos.csv": "ingresos",
        "riego.csv": "riego",
        "pozos.csv": "pozos",
        "produccion.csv": "producción",
        "labores.csv": "labores",
        "gastos_recurrentes.csv": "gastos recurrentes",
        "cosechas.csv": "cosechas",
        "presencias.csv": "presencias",
    }
    return [
        f"{labels.get(name, name)}: {count}" for name, count in imported_by_file.items()
    ]


@router.get("/", response_class=HTMLResponse)
async def import_page(
    request: Request,
    current_user: User = Depends(require_subscription),
):
    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {"request": request, "result": None},
    )


@router.post("/all.zip", response_class=HTMLResponse)
async def upload_all_zip(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    imported_by_file, warnings = await import_all_csv_zip(db, content, current_user.active_tenant_id)
    await db.commit()

    total_imported = sum(imported_by_file.values())
    details = _summarize_zip_import(imported_by_file)

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "all_zip",
                "filename": file.filename,
                "imported": total_imported,
                "warnings": warnings,
                "details": details,
            },
            "active_tab": "all_zip",
        },
    )


@router.post("/expenses", response_class=HTMLResponse)
async def upload_expenses(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_expenses_csv(db, content, current_user.active_tenant_id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "expenses",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "expenses",
        },
    )


@router.post("/incomes", response_class=HTMLResponse)
async def upload_incomes(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_incomes_csv(db, content, current_user.active_tenant_id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "incomes",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "incomes",
        },
    )


@router.post("/plots", response_class=HTMLResponse)
async def upload_plots(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_plots_csv(db, content, current_user.active_tenant_id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "plots",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "plots",
        },
    )


@router.post("/irrigation", response_class=HTMLResponse)
async def upload_irrigation(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_irrigation_csv(db, content, current_user.active_tenant_id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "irrigation",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "irrigation",
        },
    )


@router.post("/wells", response_class=HTMLResponse)
async def upload_wells(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_wells_csv(db, content, current_user.active_tenant_id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "wells",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "wells",
        },
    )


@router.post("/truffles", response_class=HTMLResponse)
async def upload_truffles(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_truffles_csv(db, content, current_user.active_tenant_id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "truffles",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "truffles",
        },
    )


@router.post("/plot_events", response_class=HTMLResponse)
async def upload_plot_events(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_plot_events_csv(db, content, current_user.active_tenant_id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "plot_events",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "plot_events",
        },
    )


@router.post("/recurring_expenses", response_class=HTMLResponse)
async def upload_recurring_expenses(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_recurring_expenses_csv(db, content, current_user.active_tenant_id)
    await db.commit()
    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "recurring_expenses",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "recurring_expenses",
        },
    )


@router.post("/harvests", response_class=HTMLResponse)
async def upload_harvests(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_harvests_csv(db, content, current_user.active_tenant_id)
    await db.commit()
    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "harvests",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "harvests",
        },
    )


@router.post("/presences", response_class=HTMLResponse)
async def upload_presences(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    content = await file.read()
    rows, warnings = await import_presences_csv(db, content, current_user.active_tenant_id)
    await db.commit()
    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "presences",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "truffles",
        },
    )
